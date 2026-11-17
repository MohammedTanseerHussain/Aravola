"""Timeline drawing: filmstrips, waveform and envelopes.

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


class TimelineRenderMixin:
    """Timeline drawing: filmstrips, waveform and envelopes."""

    def get_filmstrip_image(self, item, item_w, item_h):
        path = item.get('path')
        if not path and item['type'] != 'title': return None

        # Show placeholder while moviepy is loading in background
        if not _MOVIEPY_LOADED and item['type'] in ('video', 'title'):
            return self._placeholder_photo(item, item_w, item_h)

        num_frames = min(15, max(1, int(item_w / 60)))
        cache_key = f"filmstrip_v4_{path}_{num_frames}_{item.get('rotation',0)}_{item.get('flip_h',False)}_{item.get('flip_v',False)}_{item_w}x{item_h}_{item.get('theme', '')}_{item.get('main_text', '')}"
        
        if cache_key in self._clip_cache:
            return self._clip_cache[cache_key]

        # Filmstrip not cached yet — queue for background generation
        self._placeholder_photo(item, item_w, item_h)
        self._pending_filmstrips.append((item, item_w, item_h, cache_key, num_frames))
        self._schedule_filmstrip_bg()
        return None

    def _placeholder_photo(self, item, item_w, item_h):
        """Return a small placeholder PhotoImage for a clip not yet rendered."""
        label = item.get('name', item['type'])[:6].upper()
        ph_key = f"ph_{item.get('path','')}{item_w}x{item_h}"
        if ph_key in self._clip_cache:
            return self._clip_cache[ph_key]
        try:
            img = PIL.Image.new('RGB', (max(1, int(item_w)), int(item_h)), (30, 30, 45))
            d = ImageDraw.Draw(img)
            d.text((8, item_h // 2 - 6), label, fill=(140, 140, 160))
            photo = ImageTk.PhotoImage(img)
            self._clip_cache[ph_key] = photo
            return photo
        except Exception:
            return None

    def _schedule_filmstrip_bg(self):
        """Process pending filmstrips in a single background thread (batched)."""
        if self._filmstrip_bg_active:
            return
        self._filmstrip_bg_active = True

        def _worker():
            try:
                while self._pending_filmstrips:
                    item, item_w, item_h, cache_key, num_frames = self._pending_filmstrips.pop(0)
                    if cache_key in self._clip_cache:
                        continue
                    try:
                        self._render_filmstrip(item, item_w, item_h, cache_key, num_frames)
                    except Exception:
                        pass
            except Exception as ex:
                print("COLOR FILTER ERROR:", ex)
                import traceback; traceback.print_exc()
                self.root.after(0, self.refresh_timeline)
            finally:
                self._filmstrip_bg_active = False

        threading.Thread(target=_worker, daemon=True).start()

    def _render_filmstrip(self, item, item_w, item_h, cache_key, num_frames):
        """Render a single filmstrip (runs in background thread)."""
        path = item.get('path')
        frame_w = max(1, int(item_w / num_frames))
        strip_img = PIL.Image.new('RGB', (int(item_w), int(item_h)), (20, 20, 35))

        if item['type'] == 'image':
            img = PIL.Image.open(path).convert('RGB')
            rot = item.get('rotation', 0)
            if rot != 0: img = img.rotate(-rot, expand=True)
            if item.get('flip_h'): img = img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
            if item.get('flip_v'): img = img.transpose(PIL.Image.FLIP_TOP_BOTTOM)
            img = img.resize((frame_w, int(item_h)), PIL.Image.LANCZOS)
            for i in range(num_frames):
                strip_img.paste(img, (i * frame_w, 0))

        elif item['type'] == 'title':
            try:
                tc = self.build_finch_title_card(426, 240, item, preview_mode=True)
                sample_t = float(item.get('value', 5.0)) / 2.0
                f_arr = tc.get_frame(min(sample_t, tc.duration - 0.01))
                tc.close()
                base_thumb = PIL.Image.fromarray(f_arr)
                base_thumb = base_thumb.resize((frame_w, int(item_h)), PIL.Image.LANCZOS)
                for i in range(num_frames):
                    strip_img.paste(base_thumb, (i * frame_w, 0))
            except Exception:
                pass

        else:
            clip = VideoFileClip(path)
            dur = clip.duration if clip.duration and clip.duration > 0 else 1.0
            for i in range(num_frames):
                t = (i + 0.5) * (dur / num_frames)
                try:
                    f_img = PIL.Image.fromarray(clip.get_frame(t))
                    rot = item.get('rotation', 0)
                    if rot != 0: f_img = f_img.rotate(-rot, expand=True)
                    if item.get('flip_h'): f_img = f_img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                    if item.get('flip_v'): f_img = f_img.transpose(PIL.Image.FLIP_TOP_BOTTOM)
                    f_img = f_img.resize((frame_w, int(item_h)), PIL.Image.LANCZOS)
                    strip_img.paste(f_img, (i * frame_w, 0))
                except Exception:
                    pass
            clip.close()

        photo = ImageTk.PhotoImage(strip_img)
        self._clip_cache[cache_key] = photo

    def _draw_waveform(self, c, item, x_left, x_right, y_top, y_bot, col):
        path = item.get("path")
        if not path: return
        w_key = f"wave_{path}"
        if w_key not in self.waveforms:
            self._extract_waveform_async(item, w_key)
        wf = self.waveforms.get(w_key)
        if wf is not None and len(wf) > 0:
            step_w = max(1, (x_right - x_left) / len(wf))
            mid_y = (y_top + y_bot) / 2
            amp_max = (y_bot - y_top) / 2 - 2
            pts = []
            for k, v in enumerate(wf):
                pts.append((x_left + k * step_w, mid_y - v * amp_max))
            for k, v in reversed(list(enumerate(wf))):
                pts.append((x_left + k * step_w, mid_y + v * amp_max))
            c.create_polygon(pts, fill=col, outline="")
        elif _MOVIEPY_LOADED:
            # Waveform not yet extracted — draw a flat line as placeholder
            mid_y = (y_top + y_bot) / 2
            c.create_line(x_left, mid_y, x_right, mid_y, fill=col, dash=(2, 4))

    def _extract_waveform_async(self, item, w_key):
        """Extract waveform samples in a background thread."""
        def _worker():
            try:
                samples = extract_waveform_samples(item.get("path", ""), 200)
                self.waveforms[w_key] = samples
                self.root.after(0, self.refresh_timeline)
            except Exception:
                self.waveforms[w_key] = None
        threading.Thread(target=_worker, daemon=True).start()

    def _draw_vol_envelope_on_track(self, c, clip_dict, x_l, x_r, y_top, y_bot):
        env = clip_dict.get("vol_envelope", [])
        if not env or len(env) < 2:
            base_vol = clip_dict.get("volume", 1.0)
            env = [(0.0, base_vol), (1.0, base_vol)]
            clip_dict["vol_envelope"] = env

        MAX_VOL = 2.0
        env_s = sorted(env, key=lambda p: p[0])
        track_h = y_bot - y_top
        ease_mode = clip_dict.get('ease_mode', 'none')

        def kp_to_xy(t_frac, vol):
            kx = x_l + t_frac * (x_r - x_l)
            ky = y_bot - (vol / MAX_VOL) * track_h
            return kx, ky

        # Draw smooth curve: sample many points between each pair of keypoints
        # using the same cosine interpolation as _eval_vol_envelope so the
        # visual line matches what the audio actually does.
        STEPS = 30   # segments per keypoint span
        line_col = "#FFD700"

        for seg in range(len(env_s) - 1):
            t0, v0 = env_s[seg]
            t1, v1 = env_s[seg + 1]
            seg_pts = []
            for step in range(STEPS + 1):
                alpha_raw = step / STEPS
                # cosine ease (matches _eval_vol_envelope exactly)
                alpha = 0.5 - 0.5 * math.cos(alpha_raw * math.pi)
                vol   = v0 + alpha * (v1 - v0)
                t_frac = t0 + alpha_raw * (t1 - t0)
                seg_pts.append(kp_to_xy(t_frac, vol))
            if len(seg_pts) >= 2:
                flat = [coord for xy in seg_pts for coord in xy]
                c.create_line(*flat, fill=line_col, width=2, smooth=True)

        # Draw pt_gain ticks — red vertical spike at points with a sudden gain != 1.0
        pt_gains = clip_dict.get("pt_gains", {})
        for pt_idx, (t_frac, vol) in enumerate(env_s):
            gain = float(pt_gains.get(str(pt_idx), 1.0))
            if abs(gain - 1.0) > 0.02:   # only draw if actually changed
                kx, ky = kp_to_xy(t_frac, vol)
                spike_col = "#ff4444" if gain < 1.0 else "#44ff88"
                # Vertical spike above/below the point
                spike_h = int(track_h * 0.35)
                c.create_line(kx, ky - spike_h, kx, ky + spike_h,
                              fill=spike_col, width=2)
                c.create_text(kx + 5, ky - spike_h + 2,
                              text=f"x{gain:.2f}", fill=spike_col,
                              font=("Segoe UI", 7), anchor="w")

        # Draw keypoint markers — shape reflects ease mode
        for pt_idx, (t_frac, vol) in enumerate(env_s):
            kx, ky = kp_to_xy(t_frac, vol)
            is_anchor = (pt_idx == 0 or pt_idx == len(env_s) - 1)

            if ease_mode == 'none':
                # Default: filled circle
                c.create_oval(kx-4, ky-4, kx+4, ky+4,
                              fill=C["accent2"], outline="white", width=1)

            elif ease_mode == 'ease_in':
                if is_anchor and t_frac <= 0.01:
                    # Start point: upward-pointing triangle (ramp begins here)
                    c.create_polygon(kx, ky-6, kx-5, ky+4, kx+5, ky+4,
                                     fill="#39d353", outline="white", width=1)
                elif is_anchor and t_frac >= 0.99:
                    # End point: square (held level)
                    c.create_rectangle(kx-4, ky-4, kx+4, ky+4,
                                       fill=C["accent2"], outline="white", width=1)
                else:
                    c.create_oval(kx-4, ky-4, kx+4, ky+4,
                                  fill="#39d353", outline="white", width=1)

            elif ease_mode == 'ease_out':
                if is_anchor and t_frac <= 0.01:
                    # Start point: square (held level)
                    c.create_rectangle(kx-4, ky-4, kx+4, ky+4,
                                       fill=C["accent2"], outline="white", width=1)
                elif is_anchor and t_frac >= 0.99:
                    # End point: downward triangle (ramp ends here)
                    c.create_polygon(kx, ky+6, kx-5, ky-4, kx+5, ky-4,
                                     fill=C["accent4"], outline="white", width=1)
                else:
                    c.create_oval(kx-4, ky-4, kx+4, ky+4,
                                  fill=C["accent4"], outline="white", width=1)

            elif ease_mode == 'ease_in_out':
                if is_anchor and t_frac <= 0.01:
                    # Left arm of X — upward triangle
                    c.create_polygon(kx, ky-6, kx-5, ky+4, kx+5, ky+4,
                                     fill="#39d353", outline="white", width=1)
                elif is_anchor and t_frac >= 0.99:
                    # Right arm of X — downward triangle
                    c.create_polygon(kx, ky+6, kx-5, ky-4, kx+5, ky-4,
                                     fill=C["accent4"], outline="white", width=1)
                else:
                    # Interior hold points: diamond shape
                    c.create_polygon(kx, ky-6, kx+6, ky, kx, ky+6, kx-6, ky,
                                     fill=C["accent"], outline="white", width=1)

    def refresh_timeline(self):
        c = self.timeline_canvas
        c.delete("all")

        total_dur = self._total_duration()
        canvas_w = max(self.LABEL_W + int(total_dur * self.PPS) + 200, 900)
        canvas_h = self.RULER_H + (len(self.media_queue)+len(self.bgm_tracks)+2)*(self.TRACK_H)
        c.configure(scrollregion=(0, 0, canvas_w, canvas_h))

        c.create_rectangle(0, 0, canvas_w, self.RULER_H, fill=C["surface"], outline="")

        step = 5
        if self.PPS > 150: step = 1
        elif self.PPS < 40: step = 10

        t = 0.0
        while t <= total_dur + 10.0:
            x = self.LABEL_W + int(t * self.PPS)
            c.create_line(x, self.RULER_H-5, x, self.RULER_H, fill=C["text_dim"])
            mins = int(t) // 60
            secs = int(t) % 60
            c.create_text(x, self.RULER_H//2, text=f"{mins:02d}:{secs:02d}", fill=C["text_dim"], font=("Courier", 8))
            t += step

        c.create_rectangle(0, 0, self.LABEL_W, canvas_h, fill=C["surface"], outline="")

        y_cursor = self.RULER_H + 4

        curr_t = 0.0
        for i, item in enumerate(self.media_queue):
            item["tl_start"] = curr_t
            dur = self._item_duration(item)

            x_l = self.LABEL_W + int(curr_t * self.PPS)
            x_r = self.LABEL_W + int((curr_t + dur) * self.PPS)
            item_w = max(1, x_r - x_l)
            y_bot = y_cursor + self.TRACK_H

            is_sel = (i == self.selected_idx)
            outline_col = "white" if is_sel else C["border"]
            c.create_rectangle(x_l, y_cursor, x_r, y_bot, fill=C["clip_video"] if item["type"] != "title" else "#2a0050", outline=outline_col, width=2 if is_sel else 1)

            if item['type'] == 'placeholder' and not item.get('path'):
                c.create_text(x_l + item_w/2, y_cursor + 20, text="PLACEHOLDER", fill="#FF9800", font=("Segoe UI", 9, "bold"))
            else:
                fs_photo = self.get_filmstrip_image(item, item_w, self.TRACK_H)
                if fs_photo:
                    c.create_image(x_l, y_cursor, image=fs_photo, anchor="nw")
                if item['type'] == 'video' and not item.get('muted'):
                    self._draw_waveform(c, item, x_l, x_r, y_bot - 20, y_bot, C["waveform"])

            if item.get("mute_regions"):
                for (start, end) in item["mute_regions"]:
                    mx_l = x_l + int((start / dur) * item_w)
                    mx_r = x_l + int((end / dur) * item_w)
                    c.create_rectangle(mx_l, y_cursor, mx_r, y_bot, fill=C["clip_mute"], stipple="gray50", outline="")

            # Show highlight effect indicator on the clip
            hl_effect = item.get('_highlight_effect')
            if hl_effect:
                h_color = "#FF6F00" if hl_effect == 'slowmo_zoom' else "#7B1FA2"
                h_label = "🐌" if hl_effect == 'slowmo_zoom' else "⏪"
                # Draw colored border around the clip
                c.create_rectangle(x_l, y_cursor, x_r, y_bot, outline=h_color, width=3)
                c.create_text((x_l + x_r) // 2, y_cursor + 12, text=h_label,
                              fill="white", font=("Segoe UI Emoji", 10, "bold"), anchor="center")

            if item['type'] == 'video':
                self._draw_vol_envelope_on_track(c, item, x_l, x_r, y_cursor, y_bot)

            dur_text = f"[{item.get('clip_start', 0.0):.1f}s-{item.get('clip_end', 0.0):.1f}s]" if item['type'] == 'video' else f"{item.get('value',5.0)}s"
            if item.get('muted'): dur_text += " 🔇"
            c.create_rectangle(x_l, y_bot - 16, x_r, y_bot, fill="#111", outline="")
            c.create_text(x_l + 4, y_bot - 8, text=dur_text, fill="#aaa", font=("Segoe UI", 8), anchor="w")

            if item.get('text'):
                t_dur = max(0.1, float(item.get('value', 5.0)))
                txt_w = item_w * ((item['text_end'] - item['text_start']) / t_dur)
                txt_x = x_l + item_w * (item['text_start'] / t_dur)
                c.create_rectangle(txt_x, y_bot + 5, txt_x + txt_w, y_bot + 20, fill="#00A8FF", outline="")
                c.create_text(txt_x + 5, y_bot + 12, text="T", fill="white", font=("Segoe UI", 7, "bold"), anchor="w")

            c.create_text(self.LABEL_W//2, (y_cursor+y_bot)//2, text=f"V{i+1}", fill=C["text_dim"], font=("Arial", 8, "bold"))
            curr_t += dur

        y_cursor += self.TRACK_H + 10
        max_vid_x = self.LABEL_W + int(curr_t * self.PPS)

        c.create_line(0, y_cursor, max(2000, max_vid_x), y_cursor, fill=C["border"], dash=(4, 4))
        y_cursor += 4

        aud_h = 40
        max_aud_x = self.LABEL_W
        for j, aud in enumerate(self.bgm_tracks):
            is_spacer = aud.get('is_speech_pause_spacer', False)
            is_sel = (j == self.selected_audio_idx)
            is_multisel = (j in self._audio_multiselect)
            outline_col = "white" if is_sel else C["border"]

            t_s = aud.get('start_offset', 0.0)
            dur = self._get_bgm_played_dur(aud)

            x_l = self.LABEL_W + int(t_s * self.PPS)
            x_r = self.LABEL_W + int((t_s + dur) * self.PPS)
            y_bot = y_cursor + aud_h

            if is_spacer:
                # Draw speech-pause spacer as a hatched grey gap
                c.create_rectangle(x_l, y_cursor, x_r, y_bot,
                                   fill="#2a2a2a", outline="#555", width=1, dash=(3,3))
                mid_x = (x_l + x_r) // 2
                mid_y = (y_cursor + y_bot) // 2
                c.create_text(mid_x, mid_y, text="🎙 PAUSE",
                              fill="#FFD700", font=("Segoe UI", 7, "bold"), anchor="center")
            else:
                c.create_rectangle(x_l, y_cursor, x_r, y_bot, fill=C["clip_bgm"], outline=outline_col, width=2 if is_sel else 1)
                self._draw_waveform(c, aud, x_l, x_r, y_cursor, y_bot, C["waveform"])
                self._draw_vol_envelope_on_track(c, aud, x_l, x_r, y_cursor, y_bot)
                c.create_text(x_l + 6, y_cursor + 10, text="🎵 " + aud['name'][:20], fill="white", font=("Segoe UI", 8, "bold"), anchor="w")
                c.create_text(x_l + 6, y_cursor + 25, text=f"Vol: {aud.get('volume',1.0)*100:.0f}%", fill="#aaa", font=("Segoe UI", 7), anchor="w")
                c.create_text(self.LABEL_W//2, (y_cursor+y_bot)//2, text=f"A{j+1}", fill=C["accent3"], font=("Arial", 8, "bold"))
                if is_multisel:
                    sel_num = self._audio_multiselect.index(j) + 1
                    c.create_rectangle(x_l, y_cursor, x_r, y_bot, outline="#39d353", width=3, dash=(6,3))
                    c.create_text(x_r - 12, y_cursor + 10, text=f"⛓{sel_num}",
                                  fill="#39d353", font=("Segoe UI", 9, "bold"), anchor="e")

            y_cursor = y_bot + 2
            if x_r > max_aud_x: max_aud_x = x_r

        c.configure(scrollregion=(0, 0, max(max_vid_x, max_aud_x) + 200, y_cursor + 40))

        self._set_playhead(self.playhead_t.get(), preview=False)

        # Draw trim handles on the selected clip
        self._draw_trim_handles(c)

    def _draw_trim_handles(self, c):
        """Draw two free-floating region markers (A/B) inside the selected clip
        plus two EXTEND/SHRINK handles right at the clip's outer edges.
        The region between A/B is shaded so the user can see what will be
        deleted or split.
        """
        def draw_extend_handles(x_l, x_r, y_top, y_bot):
            # Bracket-style handles at the very edge — cyan, easy to grab,
            # visually distinct from the orange/pink A/B cut markers.
            EH = 6
            mid_y = (y_top + y_bot) // 2
            half_h = (y_bot - y_top) * 0.3
            # Left bracket "["
            c.create_line(x_l+EH, mid_y-half_h, x_l, mid_y-half_h, x_l, mid_y+half_h, x_l+EH, mid_y+half_h,
                          fill=C["accent"], width=3, tags="trim_handle")
            # Right bracket "]"
            c.create_line(x_r-EH, mid_y-half_h, x_r, mid_y-half_h, x_r, mid_y+half_h, x_r-EH, mid_y+half_h,
                          fill=C["accent"], width=3, tags="trim_handle")

        def draw_for(ctype, cidx):
            bounds = self._get_clip_bounds(ctype, cidx)
            if not bounds: return
            x_l, x_r, y_top, y_bot = bounds
            # Only draw the handles that belong to the active mode
            if self._handle_mode == "extend":
                draw_extend_handles(x_l, x_r, y_top, y_bot)
            clip_dur = self._get_clip_display_dur(ctype, cidx)
            key = (ctype, cidx)
            if self._handle_mode != "trim":
                return   # skip A/B marker drawing in extend mode

            def t_to_x(t_local):
                return x_l + int(t_local / max(0.001, clip_dur) * (x_r - x_l))

            # Draw shaded region if both markers exist
            if key in self._trim_marker_A and key in self._trim_marker_B:
                tA = self._trim_marker_A[key]
                tB = self._trim_marker_B[key]
                xA = t_to_x(min(tA, tB))
                xB = t_to_x(max(tA, tB))
                c.create_rectangle(xA, y_top, xB, y_bot,
                                   fill=C["danger"], stipple="gray25",
                                   outline="", tags="trim_handle")

            # Draw marker A
            if key in self._trim_marker_A:
                mx = t_to_x(self._trim_marker_A[key])
                c.create_line(mx, y_top, mx, y_bot,
                              fill=C["accent4"], width=3, tags="trim_handle")
                c.create_polygon(mx-5, y_top, mx+5, y_top, mx, y_top+10,
                                 fill=C["accent4"], outline="white", width=1,
                                 tags="trim_handle")
                c.create_text(mx, y_top + 14, text="A",
                              fill="white", font=("Segoe UI", 7, "bold"),
                              tags="trim_handle")

            # Draw marker B
            if key in self._trim_marker_B:
                mx = t_to_x(self._trim_marker_B[key])
                c.create_line(mx, y_top, mx, y_bot,
                              fill="#ff3cac", width=3, tags="trim_handle")
                c.create_polygon(mx-5, y_top, mx+5, y_top, mx, y_top+10,
                                 fill="#ff3cac", outline="white", width=1,
                                 tags="trim_handle")
                c.create_text(mx, y_top + 14, text="B",
                              fill="white", font=("Segoe UI", 7, "bold"),
                              tags="trim_handle")

        if self.selected_idx is not None:
            draw_for("video", self.selected_idx)
        if self.selected_audio_idx is not None:
            draw_for("audio", self.selected_audio_idx)
