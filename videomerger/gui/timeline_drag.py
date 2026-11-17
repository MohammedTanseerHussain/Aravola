"""Timeline pointer dragging, scrubbing and playhead moves.

Split mechanically from the legacy desktop application.  See
``videomerger.gui.runtime`` for shared imports and lazy MoviePy/Pygame setup.
"""
from __future__ import annotations

from .runtime import *  # noqa: F401,F403
from .runtime import (
    HAS_PYGAME,
    _HAAR_CASCADE_PATH,
    _MOVIEPY_LOADED,
    _TkExportProgressLogger,
    _ensure_moviepy,
    _ensure_pygame,
    pygame,
)


class TimelineDragMixin:
    """Timeline pointer dragging, scrubbing and playhead moves."""

    def on_tl_press(self, event):
        _ensure_pygame()
        x = self.timeline_canvas.canvasx(event.x)
        y = self.timeline_canvas.canvasy(event.y)

        self._drag_state_saved = False
        self._trim_state_saved = False
        self._close_env_popup()

        if y <= self.RULER_H + 20:
            self._is_scrubbing = True
            if HAS_PYGAME and self.is_playing and self.audio_ready:
                try: pygame.mixer.music.pause()
                except: pass
            self._set_playhead(max(0.0, (x - self.LABEL_W) / self.PPS))
            return

        if self._mute_drawing and self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)
            self._mute_draw_start_t = local_t
            return

        if self._highlight_drawing and self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)
            self._highlight_draw_start_t = local_t
            return

        # Only activate the handle type that matches the current mode button.
        # This prevents the two systems from interfering at the clip edges.
        if self._handle_mode == "extend":
            extend_hit = self._get_extend_handle_at_pos(x, y)
            if extend_hit:
                self._extend_drag = extend_hit
                self._extend_state_saved = False
                self._drag_item = None
                self._drag_env_pt = None
                self._trim_drag = None
                self._is_scrubbing = False
                return
        else:   # "trim" mode (default)
            trim_hit = self._get_trim_handle_at_pos(x, y)
            if trim_hit:
                self._trim_drag = trim_hit
                self._drag_item = None
                self._drag_env_pt = None
                self._is_scrubbing = False
                return

        pt_hit = self._get_env_pt_at_pos(x, y)
        if pt_hit:
            self._drag_env_pt = pt_hit
            self._is_scrubbing = False
            self._drag_item = None
            ctype, cidx, pt_idx = pt_hit
            self._show_env_pt_vol_popup(ctype, cidx, pt_idx, x, y)
            return

        self._drag_env_pt = None
        self._is_scrubbing = False

        # Ctrl+Click on an audio track = multiselect for Speech Ease (max 2)
        ctrl_held = bool(event.state & 0x0004)
        if ctrl_held:
            clip_info = self._get_clip_at_pos(x, y)
            if clip_info and clip_info[0] == "audio":
                cidx = clip_info[1]
                if cidx in self._audio_multiselect:
                    self._audio_multiselect.remove(cidx)
                else:
                    self._audio_multiselect.append(cidx)
                    if len(self._audio_multiselect) > 2:
                        self._audio_multiselect = self._audio_multiselect[-2:]
                self.refresh_timeline()
                return

        self.selected_idx = None
        self.selected_audio_idx = None

        clip_info = self._get_clip_at_pos(x, y)
        if clip_info:
            ctype, cidx, clip, x_l, x_r, y_top, y_bot = clip_info
            if ctype == "video":
                self.selected_idx = cidx
                self._drag_item = ("video", cidx)
                self._drag_start_x = x
                self._drag_orig_start = clip.get("tl_start", 0.0)
            else:
                self.selected_audio_idx = cidx
                self._drag_item = ("audio", cidx)
                self._drag_start_x = x
                self._drag_orig_start = clip.get("start_offset", 0.0)
            # Auto-place markers at the clip edges on selection
            key = (ctype, cidx)
            clip_dur = self._get_clip_display_dur(ctype, cidx)
            self._trim_marker_A[key] = 0.0
            self._trim_marker_B[key] = clip_dur
            self.render_inspector()
            self.refresh_effects_tab()
            self.refresh_timeline()
            return

        self.render_inspector()
        self.refresh_effects_tab()
        self.refresh_timeline()

    def on_tl_double_click(self, event):
        x = self.timeline_canvas.canvasx(event.x)
        y = self.timeline_canvas.canvasy(event.y)
        
        clip_info = self._get_clip_at_pos(x, y)
        if clip_info:
            self.save_state() 
            ctype, cidx, clip, x_l, x_r, y_top, y_bot = clip_info
            
            t_frac = float(np.clip((x - x_l) / max(1, x_r - x_l), 0.0, 1.0))
            vol = float(np.clip(2.0 * (y_bot - y) / max(1, y_bot - y_top), 0.0, 2.0))
            
            active_clip = self.media_queue[cidx] if ctype == 'video' else self.bgm_tracks[cidx]
            
            if "vol_envelope" not in active_clip or not active_clip["vol_envelope"]:
                active_clip["vol_envelope"] = [(0.0, 1.0), (1.0, 1.0)]
                
            active_clip["vol_envelope"].append((t_frac, vol))
            active_clip["vol_envelope"].sort(key=lambda p: p[0])
            
            self.timeline_dirty = True
            self.refresh_timeline()

    def on_tl_right_click(self, event):
        x = self.timeline_canvas.canvasx(event.x)
        y = self.timeline_canvas.canvasy(event.y)
        
        pt_hit = self._get_env_pt_at_pos(x, y)
        if pt_hit:
            self.save_state()
            ctype, cidx, pt_idx = pt_hit
            clip = self.media_queue[cidx] if ctype == 'video' else self.bgm_tracks[cidx]
            env = clip["vol_envelope"]
            
            if len(env) > 2:
                del env[pt_idx]
                self.timeline_dirty = True
                self.refresh_timeline()

    def _throttled_refresh_timeline(self, min_interval=0.033):
        """Same visual result as refresh_timeline(), but collapses rapid
        calls (e.g. every pixel of a mouse drag) to roughly 30fps, since
        refresh_timeline() redraws every clip/thumbnail/waveform on the
        timeline from scratch. Without this, dragging a clip, an envelope
        point, or a trim handle redraws the whole timeline on every single
        mouse-move tick, which is what makes dragging feel laggy/fiddly."""
        now = time.perf_counter()
        last = getattr(self, '_last_timeline_refresh', 0.0)
        if now - last >= min_interval:
            self._last_timeline_refresh = now
            pending = getattr(self, '_timeline_refresh_pending', None)
            if pending is not None:
                self.root.after_cancel(pending)
                self._timeline_refresh_pending = None
            self.refresh_timeline()
        elif getattr(self, '_timeline_refresh_pending', None) is None:
            delay_ms = max(1, int((min_interval - (now - last)) * 1000))
            self._timeline_refresh_pending = self.root.after(delay_ms, self._flush_timeline_refresh)

    def _flush_timeline_refresh(self):
        self._timeline_refresh_pending = None
        self._last_timeline_refresh = time.perf_counter()
        self.refresh_timeline()

    def on_tl_drag(self, event):
        x = self.timeline_canvas.canvasx(event.x)
        y = self.timeline_canvas.canvasy(event.y)

        if getattr(self, '_is_scrubbing', False):
            self._set_playhead(max(0.0, (x - self.LABEL_W) / self.PPS))
            return

        # Handle extend/shrink edge-drag (recover trimmed footage or trim further)
        if getattr(self, "_extend_drag", None):
            side, ctype, cidx = self._extend_drag
            if not self._extend_state_saved:
                self.save_state()
                self._extend_state_saved = True
            t_cursor = max(0.0, (x - self.LABEL_W) / self.PPS)
            SAFE = 0.05
            if ctype == "video":
                item = self.media_queue[cidx]
                tl_start = item.get("tl_start", 0.0)
                try:
                    if item["path"] not in self._clip_cache:
                        self._clip_cache_put(item["path"], VideoFileClip(item["path"]))
                    file_dur = self._clip_cache[item["path"]].duration
                except Exception:
                    file_dur = 999.0
                cur_cs = float(item.get("clip_start", 0.0))
                cur_ce = float(item.get("clip_end", 0.0)) or file_dur
                if side == "left":
                    # Dragging left edge: local time before tl_start moves clip_start
                    new_local = t_cursor - tl_start
                    new_cs = cur_cs + new_local   # new_local is negative when dragging outward(left)
                    item["clip_start"] = max(0.0, min(new_cs, cur_ce - SAFE))
                else:
                    new_local = t_cursor - tl_start
                    new_ce = cur_cs + new_local
                    item["clip_end"] = max(cur_cs + SAFE, min(new_ce, file_dur - SAFE))
            else:
                bgm = self.bgm_tracks[cidx]
                try:
                    if bgm["path"] not in self._clip_cache:
                        self._clip_cache_put(bgm["path"], AudioFileClip(bgm["path"]))
                    file_dur = self._clip_cache[bgm["path"]].duration
                except Exception:
                    file_dur = 999.0
                cur_cs = float(bgm.get("clip_start", 0.0))
                cur_ce = float(bgm.get("clip_end", 0.0)) or file_dur
                base_off = float(bgm.get("start_offset", 0.0))
                if side == "left":
                    new_local = t_cursor - base_off
                    new_cs = cur_cs + new_local
                    new_cs = max(0.0, min(new_cs, cur_ce - SAFE))
                    # Keep the visual start_offset anchored to where the edge is dragged to
                    delta_cs = new_cs - cur_cs
                    bgm["clip_start"] = new_cs
                    bgm["start_offset"] = base_off + delta_cs
                else:
                    new_local = t_cursor - base_off
                    new_ce = cur_cs + new_local
                    bgm["clip_end"] = max(cur_cs + SAFE, min(new_ce, file_dur - SAFE))
            self.timeline_dirty = True
            self._throttled_refresh_timeline()
            return

        # Handle trim-handle dragging
        if getattr(self, "_trim_drag", None):
            # Drag a free-floating region marker (A or B) within the clip
            marker_id, ctype, cidx = self._trim_drag
            bounds = self._get_clip_bounds(ctype, cidx)
            if bounds:
                x_l, x_r, y_top, y_bot = bounds
                clip_dur = self._get_clip_display_dur(ctype, cidx)
                # Convert canvas x → local time within the clip
                t_local = max(0.0, min(clip_dur, (x - x_l) / max(1, x_r - x_l) * clip_dur))
                key = (ctype, cidx)
                if marker_id == "A":
                    self._trim_marker_A[key] = t_local
                else:
                    self._trim_marker_B[key] = t_local
                self._throttled_refresh_timeline()   # redraw markers only, no data change
            return

        if getattr(self, '_mute_drawing', False) and self.selected_idx is not None:
            self._throttled_refresh_timeline()
            self.timeline_canvas.delete("mute_preview")
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)

            t0, t1 = sorted([self._mute_draw_start_t, local_t])
            x0 = self.LABEL_W + int((t_start + t0) * self.PPS)
            x1 = self.LABEL_W + int((t_start + t1) * self.PPS)

            y_bot = self.RULER_H + 4 + self.TRACK_H
            self.timeline_canvas.create_rectangle(x0, self.RULER_H + 4, x1, y_bot, fill=C["danger"], stipple="gray50", tags="mute_preview")
            return

        if getattr(self, '_highlight_drawing', False) and self.selected_idx is not None:
            self._throttled_refresh_timeline()
            self.timeline_canvas.delete("highlight_preview")
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)

            t0, t1 = sorted([self._highlight_draw_start_t, local_t])
            x0 = self.LABEL_W + int((t_start + t0) * self.PPS)
            x1 = self.LABEL_W + int((t_start + t1) * self.PPS)

            y_bot = self.RULER_H + 4 + self.TRACK_H
            self.timeline_canvas.create_rectangle(x0, self.RULER_H + 4, x1, y_bot, fill="#00897B", stipple="gray50", tags="highlight_preview")
            return

        if (self._drag_env_pt or self._drag_item) and not self._drag_state_saved:
            self.save_state()
            self._drag_state_saved = True

        if hasattr(self, '_drag_env_pt') and self._drag_env_pt:
            ctype, cidx, pt_idx = self._drag_env_pt
            clip = self.media_queue[cidx] if ctype == 'video' else self.bgm_tracks[cidx]
            
            clip_info = self._get_clip_bounds(ctype, cidx)
            if not clip_info: return
            x_l, x_r, y_top, y_bot = clip_info

            t_frac = np.clip((x - x_l) / max(1, x_r - x_l), 0.0, 1.0)
            vol = np.clip(2.0 * (y_bot - y) / max(1, y_bot - y_top), 0.0, 2.0)

            env = clip["vol_envelope"]
            
            if pt_idx == 0: t_frac = 0.0
            if pt_idx == len(env) - 1 and env[-1][0] == 1.0: t_frac = 1.0

            prev_t = env[pt_idx-1][0] if pt_idx > 0 else 0.0
            next_t = env[pt_idx+1][0] if pt_idx < len(env)-1 else 1.0
            t_frac = np.clip(t_frac, prev_t, next_t)

            env[pt_idx] = (t_frac, vol)

            self.timeline_dirty = True
            self._throttled_refresh_timeline()
            return

        if self._drag_item:
            itype, idx = self._drag_item

            if itype == 'video':
                t_cursor = max(0.0, (x - self.LABEL_W) / self.PPS)
                new_idx = idx
                for i, item in enumerate(self.media_queue):
                    if i == idx: continue
                    s = item.get("tl_start", 0.0)
                    e = s + self._item_duration(item)
                    if s <= t_cursor <= e:
                        new_idx = i
                        break

                if new_idx != idx:
                    item = self.media_queue.pop(idx)
                    self.media_queue.insert(new_idx, item)
                    self._drag_item = ('video', new_idx)
                    self.selected_idx = new_idx
                    self.timeline_dirty = True
                    self._throttled_refresh_timeline()
            else:
                delta_t = (x - self._drag_start_x) / self.PPS
                new_start = max(0.0, self._drag_orig_start + delta_t)
                self.bgm_tracks[idx]["start_offset"] = new_start
                self.timeline_dirty = True
                self._throttled_refresh_timeline()

    def on_tl_release(self, event):
        _ensure_pygame()
        x = self.timeline_canvas.canvasx(event.x)
        if getattr(self, '_is_scrubbing', False) and HAS_PYGAME and self.is_playing and self.audio_ready:
            try: pygame.mixer.music.unpause()
            except: pass

        if getattr(self, '_mute_drawing', False) and self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)

            t0, t1 = sorted([self._mute_draw_start_t, local_t])
            if t1 - t0 > 0.05:
                self.save_state() 
                item.setdefault("mute_regions", []).append((t0, t1))
            self._mute_drawing = False
            self.tl_mode_label.config(text="")
            self.timeline_dirty = True
            self.refresh_timeline()
            self.render_inspector()
            return

        if getattr(self, '_highlight_drawing', False) and self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)

            t0, t1 = sorted([self._highlight_draw_start_t, local_t])
            self._highlight_drawing = False
            self.tl_mode_label.config(text="")
            if t1 - t0 > 0.1:
                self.save_state()
                self._split_and_duplicate_highlight(self.selected_idx, t0, t1)
            else:
                self.refresh_timeline()
            return

        self._is_scrubbing = False
        was_dragging = bool(self._drag_item or self._drag_env_pt or self._trim_drag or self._extend_drag)
        self._drag_item = None
        self._drag_env_pt = None
        self._drag_state_saved = False
        self._trim_drag = None
        self._trim_state_saved = False
        self._extend_drag = None
        self._extend_state_saved = False
        if was_dragging:
            # Guarantee the final position is drawn immediately — in-drag
            # redraws are throttled for smoothness, so the very last one
            # might otherwise still be sitting in a pending `after()` call.
            if getattr(self, '_timeline_refresh_pending', None) is not None:
                self.root.after_cancel(self._timeline_refresh_pending)
                self._timeline_refresh_pending = None
            self.refresh_timeline()

    def _set_playhead(self, t, preview=True):
        self.playhead_t.set(t)

        mins = int(t) // 60
        secs = int(t) % 60
        ms = int((t % 1) * 100)
        self.timecode_var.set(f"{mins:02d}:{secs:02d}.{ms:02d}")

        c = self.timeline_canvas
        c.delete("playhead_line")
        c.delete("playhead_poly")

        ph_x = self.LABEL_W + int(t * self.PPS)
        c.create_line(ph_x, 0, ph_x, 2000, fill=C["accent"], width=2, tags="playhead_line")
        c.create_polygon(ph_x-6, 0, ph_x+6, 0, ph_x, 10, fill=C["accent"], tags="playhead_poly")

        if preview:
            self._interactive_mode = True
            if self._preview_job is not None:
                self.root.after_cancel(self._preview_job)
            self._preview_job = self.root.after(16, self.update_global_preview)
            # Settle to a full-quality render shortly after scrubbing stops,
            # same pattern used for slider drags and 3D-text editing.
            if self._final_preview_job is not None:
                self.root.after_cancel(self._final_preview_job)
            self._final_preview_job = self.root.after(350, self._run_final_preview)
