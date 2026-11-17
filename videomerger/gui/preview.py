"""Full-resolution preview and clip-frame composition.

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


class PreviewMixin:
    """Full-resolution preview and clip-frame composition."""

    def update_global_preview(self):
        if not _MOVIEPY_LOADED:
            return
        t = self.playhead_t.get()
        active_item = None
        local_t = 0.0

        for item in self.media_queue:
            start = item.get("tl_start", 0.0)
            dur = self._item_duration(item)
            if start <= t < start + dur:
                active_item = item
                # For highlight clips, don't apply speed here — handle it below
                if item.get('_highlight_effect'):
                    local_t = t - start
                else:
                    local_t = (t - start) * item.get("speed", 1.0)
                break

        if not active_item:
            self.preview_label.config(image='', text="● PLAYBACK  (No clip at this position)", fg="#333333")
            return

        try:
            is_mobile = (self.format_var.get() == "mobile")
            # Low-res mode for interactive slider dragging — half the normal res
            if self._interactive_mode:
                target_w = 270 if is_mobile else 480
                target_h = 480 if is_mobile else 270
            else:
                target_w = 540 if is_mobile else 960
                target_h = 960 if is_mobile else 540
            scale_val = active_item.get('scale', 1.0)
            text_3d_enabled = active_item.get('effect_3d_text_enabled', False)

            if active_item['type'] == 'title':
                clip = self.build_finch_title_card(target_w, target_h, active_item, preview_mode=True)
                clip_dur = clip.duration
                if active_item.get('text'):
                    t_start = active_item.get('text_start', 0.0)
                    t_end = active_item.get('text_end', 3.0)
                    if t_start <= local_t <= t_end:
                        lt_t = local_t - t_start
                        lt_dur = t_end - t_start
                        lt_style = active_item.get('lt_style', 'News Headline')
                        if lt_style == 'News Headline':
                            lt_layers = self.build_news_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                        elif lt_style == 'Purple Designer Box':
                            lt_layers = self.build_designer_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                        elif lt_style == 'Static Aurora Tile (Bracket)':
                            lt_layers = self.build_tile_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                        else:
                            lt_layers = self.build_magical_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                        comp = CompositeVideoClip([clip.set_duration(clip_dur)] + [l.set_start(0.0) for l in lt_layers], size=(target_w, target_h)).set_duration(clip_dur)
                        frame_array = comp.get_frame(min(lt_t, comp.duration - 0.01))
                        comp.close()
                    else:
                        frame_array = clip.get_frame(min(local_t, clip.duration - 0.01))
                else:
                    frame_array = clip.get_frame(min(local_t, clip.duration - 0.01))
                img = PIL.Image.fromarray(frame_array)
                clip.close()
            else:
                if active_item['type'] == 'video' and active_item.get('path'):
                    if active_item['path'] not in self._clip_cache:
                        self._clip_cache_put(active_item['path'], VideoFileClip(active_item['path']))
                    raw = self._clip_cache[active_item['path']]
                    read_t = active_item.get('clip_start', 0.0) + local_t

                    # --- HIGHLIGHT CLIP EFFECT (PREVIEW) ---
                    hl_effect = active_item.get('_highlight_effect')
                    if hl_effect == 'reverse':
                        # Show reversed time within the clip
                        clip_dur = self._item_duration(active_item)
                        read_t = active_item.get('clip_start', 0.0) + (clip_dur - local_t)
                    elif hl_effect == 'slowmo_zoom':
                        speed = max(0.1, active_item.get('speed', 0.3))
                        read_t = active_item.get('clip_start', 0.0) + local_t * speed

                    if raw.duration is not None:
                        read_t = max(0.0, min(read_t, raw.duration - 0.01))
                    read_t = max(0.0, read_t)
                    frame = raw.get_frame(read_t)
                    base_img = PIL.Image.fromarray(frame)

                    # Apply slowmo_zoom visual zoom effect (skip in interactive/low-res mode)
                    if hl_effect == 'slowmo_zoom' and not self._interactive_mode:
                        zoom_level = active_item.get('_highlight_zoom', 1.5)
                        clip_dur = self._item_duration(active_item)
                        if clip_dur > 0.01:
                            region_progress = local_t / clip_dur
                            current_zoom = 1.0 + (zoom_level - 1.0) * min(1.0, region_progress * 1.5)
                            w, h = base_img.size
                            new_w = max(1, int(w * current_zoom))
                            new_h = max(1, int(h * current_zoom))
                            zoomed = base_img.resize((new_w, new_h), PIL.Image.BILINEAR)
                            left = (new_w - w) // 2
                            top = (new_h - h) // 2
                            base_img = zoomed.crop((left, top, left + w, top + h))

                    rot = active_item.get('rotation', 0)
                    if rot != 0: base_img = base_img.rotate(-rot, expand=True)
                    if active_item.get('flip_h', False): base_img = base_img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                    if active_item.get('flip_v', False): base_img = base_img.transpose(PIL.Image.FLIP_TOP_BOTTOM)

                    base_clip = ImageClip(np.array(base_img))
                    if self.auto_rotate_var.get():
                        if target_w > target_h and base_clip.w < base_clip.h: base_clip = self.safe_transform(base_clip, 90, False, False)
                        elif target_w < target_h and base_clip.w > base_clip.h: base_clip = self.safe_transform(base_clip, -90, False, False)

                    ken_burns = active_item.get('ken_burns_enabled', False)
                    if self.smart_fill_var.get():
                        base_sf = max(target_w / base_clip.w, target_h / base_clip.h) * scale_val
                    else:
                        base_sf = min(target_w / base_clip.w, target_h / base_clip.h) * scale_val

                    if ken_burns:
                        clip_dur = max(self._item_duration(active_item), 0.01)
                        t_prog = min(local_t / clip_dur, 1.0)
                        kb_zoom_in = float(active_item.get('ken_burns_zoom_in', 1.0))
                        kb_zoom_out = float(active_item.get('ken_burns_zoom_out', 1.3))
                        kb_pan_x = float(active_item.get('ken_burns_pan_x', 0.0))
                        kb_pan_y = float(active_item.get('ken_burns_pan_y', 0.0))
                        zoom = kb_zoom_in + (kb_zoom_out - kb_zoom_in) * t_prog

                        fit_w = int(base_clip.w * base_sf)
                        fit_h = int(base_clip.h * base_sf)
                        ref_clip = base_clip.fx(vfx.resize, base_sf).fx(
                            vfx.crop, x_center=fit_w / 2, y_center=fit_h / 2, width=target_w, height=target_h)
                        ref_frame = ref_clip.get_frame(0)
                        ref_clip.close()

                        # NOTE: 3D text is intentionally NOT composited here — it's
                        # applied later, on the already-zoomed final frame, at a
                        # fixed size/position. That keeps it a flat, fixed-size
                        # marker (like an AR doodle) instead of scaling up with
                        # the Ken Burns zoom.
                        zoomed = self._apply_kenburns_zoom_numpy(
                            ref_frame, zoom, kb_pan_x, kb_pan_y, t_prog, target_w, target_h)
                        base_clip = ImageClip(zoomed)
                    elif self.smart_fill_var.get():
                        new_w = int(base_clip.w * base_sf)
                        new_h = int(base_clip.h * base_sf)
                        base_clip = base_clip.fx(vfx.resize, base_sf).fx(vfx.crop, x_center=new_w/2, y_center=new_h/2, width=target_w, height=target_h)
                    else:
                        base_clip = base_clip.fx(vfx.resize, base_sf)

                    vlayers = [ColorClip(size=(target_w, target_h), color=(0, 0, 0)).set_duration(1.0), base_clip.set_position("center")]

                    lt_t = 0.0
                    if active_item.get('text'):
                        t_start = active_item.get('text_start', 0.0)
                        t_end = active_item.get('text_end', 3.0)
                        if t_start <= local_t <= t_end:
                            lt_t = local_t - t_start
                            lt_dur = t_end - t_start
                            lt_style = active_item.get('lt_style', 'Static Aurora Tile (Bracket)')
                            if lt_style == 'Purple Designer Box':
                                lt_layers = self.build_designer_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                            elif lt_style == 'Static Aurora Tile (Bracket)':
                                lt_layers = self.build_tile_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                            else:
                                lt_layers = self.build_magical_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                            vlayers.extend([l.set_start(0.0) for l in lt_layers])

                    comp = CompositeVideoClip(vlayers, size=(target_w, target_h))
                    frame_array = comp.get_frame(lt_t)
                    img = PIL.Image.fromarray(frame_array)
                    comp.close()
                    base_clip.close()

                elif active_item['type'] == 'image' and active_item.get('path'):
                    img_path = active_item['path']
                    if img_path not in self._img_cache:
                        self._img_cache[img_path] = PIL.Image.open(img_path).convert("RGB").copy()
                        if len(self._img_cache) > 20:
                            first_key = next(iter(self._img_cache))
                            del self._img_cache[first_key]
                    base_img = self._img_cache[img_path].copy()
                    rot = active_item.get('rotation', 0)
                    if rot != 0: base_img = base_img.rotate(-rot, expand=True)
                    if active_item.get('flip_h', False): base_img = base_img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                    if active_item.get('flip_v', False): base_img = base_img.transpose(PIL.Image.FLIP_TOP_BOTTOM)
                    ken_burns = active_item.get('ken_burns_enabled', False)
                    if self.smart_fill_var.get():
                        base_sf = max(target_w / base_img.width, target_h / base_img.height) * scale_val
                    else:
                        base_sf = min(target_w / base_img.width, target_h / base_img.height) * scale_val

                    if ken_burns:
                        clip_dur = max(self._item_duration(active_item), 0.01)
                        t_prog = min(local_t / clip_dur, 1.0)
                        kb_zoom_in = float(active_item.get('ken_burns_zoom_in', 1.0))
                        kb_zoom_out = float(active_item.get('ken_burns_zoom_out', 1.3))
                        kb_pan_x = float(active_item.get('ken_burns_pan_x', 0.0))
                        kb_pan_y = float(active_item.get('ken_burns_pan_y', 0.0))
                        zoom = kb_zoom_in + (kb_zoom_out - kb_zoom_in) * t_prog

                        fit_w = max(1, int(round(base_img.width * base_sf)))
                        fit_h = max(1, int(round(base_img.height * base_sf)))
                        fitted = base_img.resize((fit_w, fit_h), PIL.Image.LANCZOS)
                        ref_canvas = PIL.Image.new("RGB", (target_w, target_h), (0, 0, 0))
                        ref_canvas.paste(fitted, ((target_w - fit_w) // 2, (target_h - fit_h) // 2))
                        ref_frame = np.array(ref_canvas)

                        # NOTE: 3D text is intentionally NOT composited here — it's
                        # applied later, on the already-zoomed final frame, at a
                        # fixed size/position. That keeps it a flat, fixed-size
                        # marker (like an AR doodle) instead of scaling up with
                        # the Ken Burns zoom.
                        zoomed = self._apply_kenburns_zoom_numpy(
                            ref_frame, zoom, kb_pan_x, kb_pan_y, t_prog, target_w, target_h)
                        base_img = PIL.Image.fromarray(zoomed)
                    elif self.smart_fill_var.get():
                        sf = base_sf
                        base_img = base_img.resize((int(base_img.width * sf), int(base_img.height * sf)), PIL.Image.LANCZOS)
                        left = (base_img.width - target_w) // 2
                        top = (base_img.height - target_h) // 2
                        base_img = base_img.crop((left, top, left + target_w, top + target_h))
                    else:
                        sf = base_sf
                        base_img = base_img.resize((int(base_img.width * sf), int(base_img.height * sf)), PIL.Image.LANCZOS)
                    img = base_img

                else:
                    base_img = PIL.Image.new("RGB", (target_w, target_h), (20, 20, 20))
                    ImageDraw.Draw(base_img).text((100, 150), "PLACEHOLDER", fill=(200, 100, 0))
                    img = base_img

            if self._mask_edit_active or self._show_outline_var.get() or (active_item.get('effect') == 'gold_outline' and self.effect_global_enabled.get()):
                if self._show_outline_var.get():
                    frame_arr = np.array(img)
                    h_f, w_f = frame_arr.shape[:2]
                    painting = active_item.get('effect_mask_painting')
                    if painting is not None:
                        ph_p, pw_p = painting.shape[:2]
                        if ph_p != h_f or pw_p != w_f:
                            paint_resized = cv2.resize(painting, (w_f, h_f), interpolation=cv2.INTER_LINEAR)
                        else:
                            paint_resized = painting
                    else:
                        paint_resized = np.ones((h_f, w_f), dtype=np.float32)
                    erase_edges = np.zeros((h_f, w_f), dtype=np.float32)
                    draw_edges = np.zeros((h_f, w_f), dtype=np.float32)
                    if self._mask_edit_active and painting is not None:
                        person_mask = active_item.get('effect_editing_base_mask')
                        if person_mask is not None and person_mask.max() > 0:
                            if person_mask.shape[:2] != (h_f, w_f):
                                person_mask = cv2.resize(person_mask, (w_f, h_f), interpolation=cv2.INTER_LINEAR)
                            orig_uint8 = (np.clip(person_mask, 0, 1) * 255).astype(np.uint8)
                            erase_edges = cv2.Canny(orig_uint8, 30, 90)
                            erase_edges = cv2.dilate(erase_edges, np.ones((3, 3), np.uint8), iterations=1)
                            erase_edges = cv2.GaussianBlur(erase_edges, (3, 3), 0).astype(np.float32) / 255.0
                            erase_edges = erase_edges * np.clip(paint_resized, 0, 1)
                    drawn = active_item.get('effect_drawn_mask')
                    if drawn is not None:
                        dw, ddh = drawn.shape[:2]
                        if ddh != h_f or dw != w_f:
                            drawn_resized = cv2.resize(drawn, (w_f, h_f), interpolation=cv2.INTER_LINEAR)
                        else:
                            drawn_resized = drawn
                        drawn_uint8 = (np.clip(drawn_resized, 0, 1) * 255).astype(np.uint8)
                        draw_edges = cv2.Canny(drawn_uint8, 30, 90)
                        draw_edges = cv2.dilate(draw_edges, np.ones((3, 3), np.uint8), iterations=1)
                        draw_edges = cv2.GaussianBlur(draw_edges, (3, 3), 0).astype(np.float32) / 255.0
                    edges = np.maximum(erase_edges, draw_edges)
                    overlay = frame_arr.copy().astype(np.float32)
                    green = np.array([0.0, 1.0, 0.0], dtype=np.float32).reshape(1, 1, 3)
                    overlay = overlay + edges[..., np.newaxis] * green * 250.0
                    overlay = np.clip(overlay, 0, 255).astype(np.uint8)
                    img = PIL.Image.fromarray(overlay)
                else:
                    frame_arr = np.array(img)
                    frame_arr = self.apply_dreamy_angel_effect(frame_arr, active_item, local_t)
                    img = PIL.Image.fromarray(frame_arr)

            thug_enabled = active_item.get('effect_thug_life_enabled', False)
            if thug_enabled and not self._interactive_mode:
                frame_arr = np.array(img)
                frame_arr = self.apply_thug_life_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            film_burn_enabled = active_item.get('effect_film_burn_enabled', False)
            if film_burn_enabled and not self._interactive_mode:
                frame_arr = np.array(img)
                frame_arr = self.apply_film_burn_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            sun_glare_enabled = active_item.get('effect_sun_glare_enabled', False)
            if sun_glare_enabled and not self._interactive_mode:
                frame_arr = np.array(img)
                frame_arr = self.apply_sun_glare_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            x_flare_enabled = active_item.get('effect_x_flare_enabled', False)
            if x_flare_enabled and not self._interactive_mode:
                frame_arr = np.array(img)
                frame_arr = self.apply_x_flare_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            light_flash_enabled = active_item.get('effect_light_flash_enabled', False)
            if light_flash_enabled and not self._interactive_mode:
                frame_arr = np.array(img)
                frame_arr = self.apply_light_flash_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            canopy_enabled = active_item.get('effect_canopy_enabled', False)
            if canopy_enabled:
                frame_arr = np.array(img)
                frame_arr = self.apply_canopy_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            # ── 3D TEXT TRACKING ──────────────────────────────────────────
            # Always applied on the final (already-zoomed/panned) frame, at a
            # fixed size and position — a flat AR-doodle-style marker that
            # doesn't scale with any Ken Burns zoom on the clip. Whether it's
            # visible right now is decided inside apply_3d_text_tracking_effect
            # (the "WHEN IT'S VISIBLE" start/end/fade settings).
            try:
                if text_3d_enabled:
                    frame_arr = np.array(img)
                    frame_arr = self.apply_3d_text_tracking_effect(frame_arr, active_item, local_t)
                    img = PIL.Image.fromarray(frame_arr)
            except Exception as ex:
                print("3D Text Tracking error:", ex)
                import traceback; traceback.print_exc()

            # Draw the move/resize/rotate handles when actively editing this clip's text
            try:
                if (getattr(self, '_3d_text_place_active', False) and self.selected_idx is not None
                        and self.media_queue[self.selected_idx] is active_item):
                    img = self._draw_3d_text_handles(img, active_item)
            except Exception:
                pass
            # ─────────────────────────────────────────────────────────────────

            # ── MOTION TRACK (arrow + name tracking) ────────────────────────
            try:
                if active_item.get('effect_motion_track_enabled', False):
                    frame_arr = np.array(img)
                    frame_arr = self.apply_motion_track_effect(frame_arr, active_item, local_t)
                    img = PIL.Image.fromarray(frame_arr)
            except Exception as ex:
                print("Motion Track error:", ex)
                import traceback; traceback.print_exc()
            # ─────────────────────────────────────────────────────────────────

            # ── COLOR FILTER ────────────────────────────────────────────────
            try:
                filter_enabled = self._filter_global_enabled.get()
                per_clip = active_item.get('filter_enabled', False)
                if per_clip:
                    filter_enabled = True
                if filter_enabled:
                    frame_arr = np.array(img)
                    if per_clip:
                        fs = active_item.get('filter_style', 'Cinematic Warm')
                        fi = active_item.get('filter_intensity', 1.0)
                        fw = active_item.get('filter_warmth', 0.5)
                        fsat = active_item.get('filter_saturation', 1.0)
                        fb = active_item.get('filter_fade_blacks', 0.15)
                    else:
                        fs = self._filter_style.get()
                        fi = self._filter_intensity.get()
                        fw = self._filter_warmth.get()
                        fsat = self._filter_saturation.get()
                        fb = self._filter_fade_blacks.get()
                    frame_arr = self.apply_color_filter(frame_arr, fs, fi, fw, fsat, fb)
                    img = PIL.Image.fromarray(frame_arr)
            except Exception:
                pass
            # ─────────────────────────────────────────────────────────────────

            # ── TRANSITION BLENDING ──────────────────────────────────────────
            try:
                img = self._apply_transition_blend(img, t, target_w, target_h)
            except Exception:
                pass
            # ─────────────────────────────────────────────────────────────────

            # Cache full-res frame BEFORE thumbnailing — used by person click
            # detection so YOLO runs on the exact same frame the user sees.
            self._preview_full_frame = np.array(img)

            pw = max(self.preview_label.winfo_width(), 320)
            ph = max(self.preview_label.winfo_height(), 180)
            img.thumbnail((pw, ph), PIL.Image.LANCZOS)
            # Store actual display dimensions for click/box coordinate mapping
            self._preview_disp_w, self._preview_disp_h = img.size
            self._preview_label_w = pw
            self._preview_label_h = ph
            self._preview_offset_x = (pw - self._preview_disp_w) // 2
            self._preview_offset_y = (ph - self._preview_disp_h) // 2

            self.preview_img = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self.preview_img, text="")
        except Exception as ex:
            print("PREVIEW ERROR:", ex)
            traceback.print_exc()

    def _render_clip_frame(self, item, local_t, target_w, target_h, is_mobile):
        """Render a single frame from *item* at *local_t* into a PIL Image
        sized to (target_w, target_h).  Handles video, image, and title clips
        including rotation, flip, scale, smart-fill and Ken Burns."""
        scale_val = item.get('scale', 1.0)
        if item['type'] == 'title':
            clip = self.build_finch_title_card(target_w, target_h, item, preview_mode=True)
            clip_dur = clip.duration if clip.duration is not None else 5.0
            if item.get('text'):
                t_start = item.get('text_start', 0.0)
                t_end = item.get('text_end', 3.0)
                if t_start <= local_t <= t_end:
                    lt_t = local_t - t_start
                    lt_dur = t_end - t_start
                    lt_style = item.get('lt_style', 'News Headline')
                    if lt_style == 'News Headline':
                        lt_layers = self.build_news_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                    elif lt_style == 'Purple Designer Box':
                        lt_layers = self.build_designer_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                    elif lt_style == 'Static Aurora Tile (Bracket)':
                        lt_layers = self.build_tile_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                    else:
                        lt_layers = self.build_magical_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                    comp = CompositeVideoClip([clip.set_duration(clip_dur)] + [l.set_start(0.0) for l in lt_layers], size=(target_w, target_h)).set_duration(clip_dur)
                    comp_dur = comp.duration if comp.duration is not None else clip_dur
                    frame_array = comp.get_frame(min(lt_t, max(0.01, comp_dur) - 0.01))
                    comp.close()
                else:
                    frame_array = clip.get_frame(min(max(0, local_t), max(0.01, clip_dur) - 0.01))
            else:
                frame_array = clip.get_frame(min(max(0, local_t), max(0.01, clip_dur) - 0.01))
            img = PIL.Image.fromarray(frame_array)
            clip.close()
            return img

        if item['type'] == 'video' and item.get('path'):
            if item['path'] not in self._clip_cache:
                self._clip_cache_put(item['path'], VideoFileClip(item['path']))
            raw = self._clip_cache[item['path']]
            read_t = item.get('clip_start', 0.0) + local_t
            if raw.duration is not None:
                read_t = min(read_t, raw.duration - 0.01)
            frame = raw.get_frame(max(0, read_t))
            base_img = PIL.Image.fromarray(frame)
        elif item['type'] == 'image' and item.get('path'):
            img_path = item['path']
            if img_path not in self._img_cache:
                self._img_cache[img_path] = PIL.Image.open(img_path).convert("RGB").copy()
                if len(self._img_cache) > 20:
                    first_key = next(iter(self._img_cache))
                    del self._img_cache[first_key]
            base_img = self._img_cache[img_path].copy()
        else:
            base_img = PIL.Image.new("RGB", (target_w, target_h), (20, 20, 20))
            ImageDraw.Draw(base_img).text((100, 150), "PLACEHOLDER", fill=(200, 100, 0))
            return base_img

        rot = item.get('rotation', 0)
        if rot != 0:
            base_img = base_img.rotate(-rot, expand=True)
        if item.get('flip_h', False):
            base_img = base_img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
        if item.get('flip_v', False):
            base_img = base_img.transpose(PIL.Image.FLIP_TOP_BOTTOM)

        base_clip = ImageClip(np.array(base_img))
        if self.auto_rotate_var.get():
            if target_w > target_h and base_clip.w < base_clip.h:
                base_clip = self.safe_transform(base_clip, 90, False, False)
            elif target_w < target_h and base_clip.w > base_clip.h:
                base_clip = self.safe_transform(base_clip, -90, False, False)

        if self.smart_fill_var.get():
            base_sf = max(target_w / base_clip.w, target_h / base_clip.h) * scale_val
        else:
            base_sf = min(target_w / base_clip.w, target_h / base_clip.h) * scale_val

        ken_burns = item.get('ken_burns_enabled', False)
        clip_dur = max(self._item_duration(item), 0.01)
        if ken_burns:
            t_prog = min(local_t / clip_dur, 1.0)
            kb_zoom_in = float(item.get('ken_burns_zoom_in', 1.0))
            kb_zoom_out = float(item.get('ken_burns_zoom_out', 1.3))
            kb_pan_x = float(item.get('ken_burns_pan_x', 0.0))
            kb_pan_y = float(item.get('ken_burns_pan_y', 0.0))
            zoom = kb_zoom_in + (kb_zoom_out - kb_zoom_in) * t_prog
            total_sf = base_sf * zoom
            new_w = int(base_clip.w * total_sf)
            new_h = int(base_clip.h * total_sf)
            offset_x = kb_pan_x * target_w * 0.5 * t_prog
            offset_y = kb_pan_y * target_h * 0.5 * t_prog
            cx = new_w / 2 + offset_x
            cy = new_h / 2 + offset_y
            base_clip = base_clip.fx(vfx.resize, total_sf).fx(vfx.crop, x_center=cx, y_center=cy, width=target_w, height=target_h)
        elif self.smart_fill_var.get():
            new_w = int(base_clip.w * base_sf)
            new_h = int(base_clip.h * base_sf)
            base_clip = base_clip.fx(vfx.resize, base_sf).fx(vfx.crop, x_center=new_w/2, y_center=new_h/2, width=target_w, height=target_h)
        else:
            base_clip = base_clip.fx(vfx.resize, base_sf)

        vlayers = [ColorClip(size=(target_w, target_h), color=(0, 0, 0)).set_duration(clip_dur), base_clip.set_position("center")]
        if item.get('text'):
            t_start = item.get('text_start', 0.0)
            t_end = item.get('text_end', 3.0)
            if t_start <= local_t <= t_end:
                lt_dur = t_end - t_start
                lt_style = item.get('lt_style', 'Static Aurora Tile (Bracket)')
                if lt_style == 'Purple Designer Box':
                    lt_layers = self.build_designer_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                elif lt_style == 'Static Aurora Tile (Bracket)':
                    lt_layers = self.build_tile_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                else:
                    lt_layers = self.build_magical_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                vlayers.extend([l.set_start(0.0) for l in lt_layers])
        comp = CompositeVideoClip(vlayers, size=(target_w, target_h))
        comp_dur = comp.duration if comp.duration is not None else clip_dur
        frame_array = comp.get_frame(min(max(0, local_t), max(0.01, comp_dur) - 0.01))
        img = PIL.Image.fromarray(frame_array)
        comp.close()
        base_clip.close()
        return img
