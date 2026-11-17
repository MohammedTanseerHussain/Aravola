"""Person selection and mask-painting interaction.

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


class TrackingUIMixin:
    """Person selection and mask-painting interaction."""

    def _start_person_correct_mode(self):
        """Like _start_person_select_mode, but the next click CORRECTS the
        already-selected object's position at the CURRENT frame instead of
        starting a brand new selection: earlier frames' already-tracked
        positions are left untouched, and the tracking chain re-anchors
        from this frame forward using the corrected point."""
        self._person_select_is_correction = True
        self._start_person_select_mode()
        try:
            self._person_status_label.config(
                text="Click the correct position for this frame onward...", fg=C["accent"])
        except Exception:
            pass

    def _start_person_select_mode(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        if item['type'] not in ('video', 'image', 'placeholder') or not item.get('path'):
            return
        self._person_select_mode = True
        self._person_status_label.config(
            text="Click on any object in the preview...", fg=C["accent"])
        try:
            self.preview_label.config(cursor="crosshair")
            self.preview_label.bind("<ButtonPress-1>", self._on_person_click)
        except Exception:
            pass

    def _on_person_click(self, event):
        if not self._person_select_mode or self.selected_idx is None:
            return
        self._person_select_mode = False
        self.preview_label.config(cursor="")
        self.preview_label.unbind("<ButtonPress-1>")
        is_correction = getattr(self, '_person_select_is_correction', False)
        self._person_select_is_correction = False

        item = self.media_queue[self.selected_idx]
        if item['type'] not in ('video', 'image', 'placeholder') or not item.get('path'):
            return

        try:
            # Force a preview render NOW so _preview_full_frame is fresh
            # and matches exactly what the user sees on screen.
            self.update_global_preview()
            self.root.update_idletasks()

            frame = getattr(self, '_preview_full_frame', None)
            if frame is None:
                self._person_status_label.config(text="Could not read frame.", fg=C["danger"])
                return
            h_frame, w_frame = frame.shape[:2]

            # Use stored display dimensions from the last preview render
            disp_w = getattr(self, '_preview_disp_w', None)
            disp_h = getattr(self, '_preview_disp_h', None)
            ox = getattr(self, '_preview_offset_x', 0)
            oy = getattr(self, '_preview_offset_y', 0)

            if disp_w is None or disp_h is None:
                pw = max(self.preview_label.winfo_width(), 320)
                ph = max(self.preview_label.winfo_height(), 180)
                img_aspect = w_frame / max(1, h_frame)
                label_aspect = pw / max(1, ph)
                if img_aspect > label_aspect:
                    disp_w = pw
                    disp_h = int(pw / img_aspect)
                else:
                    disp_h = ph
                    disp_w = int(ph * img_aspect)
                ox = (pw - disp_w) // 2
                oy = (ph - disp_h) // 2

            # Map click from label → thumbnail → frame
            thumb_x = event.x - ox
            thumb_y = event.y - oy
            if thumb_x < 0 or thumb_x > disp_w or thumb_y < 0 or thumb_y > disp_h:
                self._person_status_label.config(text="Click inside the image.", fg=C["danger"])
                return
            click_x = int((thumb_x / max(1, disp_w)) * w_frame)
            click_y = int((thumb_y / max(1, disp_h)) * h_frame)

            print(f"[PERSON-SELECT] frame={w_frame}x{h_frame} disp={disp_w}x{disp_h} offset=({ox},{oy}) click_label=({event.x},{event.y}) click_frame=({click_x},{click_y})")

            # ── Also probe a NATIVE-RESOLUTION frame for tiny/distant subjects ──
            # The on-screen preview (and everything the live tracker compares
            # against later) works in a capped canvas size (e.g. 960x540). A
            # player who is small and distant in a wide broadcast shot can
            # shrink to just a handful of pixels there, too few to detect
            # reliably. Running YOLO a SECOND time on the full native-
            # resolution frame catches those -- but its boxes come back in
            # native pixel space, so they're converted back into the SAME
            # canvas coordinate space as everything below before being used.
            # (Using the native-res coordinates directly, unconverted, is
            # what caused the tracked arrow to drift to a neighbouring
            # person right after selection -- the stored position and the
            # live tracker's frame were in two different pixel scales.)
            hires_candidates = []
            try:
                no_transform = (
                    item.get('rotation', 0) == 0
                    and not item.get('flip_h', False)
                    and not item.get('flip_v', False)
                    and float(item.get('scale', 1.0)) == 1.0
                    and not item.get('ken_burns_enabled', False)
                    and not self.smart_fill_var.get()
                )
                if no_transform:
                    hi_frame = self._get_preview_frame(item)
                    if hi_frame is not None:
                        hi_h, hi_w = hi_frame.shape[:2]
                        fit_sf = min(w_frame / hi_w, h_frame / hi_h)
                        pad_x = (w_frame - hi_w * fit_sf) / 2.0
                        pad_y = (h_frame - hi_h * fit_sf) / 2.0
                        for p in self._yolo_track(hi_frame):
                            hx, hy, hw, hh = p['bbox']
                            cbw = max(1, int(hw * fit_sf))
                            cbh = max(1, int(hh * fit_sf))
                            cbx = int(hx * fit_sf + pad_x)
                            cby = int(hy * fit_sf + pad_y)
                            hires_candidates.append({
                                **p,
                                'bbox': (cbx, cby, cbw, cbh),
                                'center': (int(cby + cbh / 2), int(cbx + cbw / 2)),
                                'area': cbw * cbh,
                                'raw_mask': None,  # regenerate from the canvas frame, not the hi-res one
                                'mask': None,
                            })
                        if hires_candidates:
                            print(f"[PERSON-SELECT] native-res pass ({hi_w}x{hi_h}) found {len(hires_candidates)} candidate(s), mapped back to canvas space")
            except Exception as _hi_ex:
                print("Native-res detection pass skipped:", _hi_ex)
            # ─────────────────────────────────────────────────────────────

            # Find the object AT the click using YOLO-seg instance masks.
            # Prefer an object whose bounding box actually CONTAINS the
            # click point -- this is what fixes clicks landing on the wrong
            # nearby player. Comparing only to each object's CENTER (the
            # old behaviour) would happily jump to a neighbouring person
            # whenever their center happened to be closer than the person
            # whose body was actually clicked on.
            yolo_objects = self._yolo_track(frame) + hires_candidates
            if yolo_objects:
                containing = []
                for i, p in enumerate(yolo_objects):
                    bx, by, bw, bh = p['bbox']
                    pad = max(2, int(min(bw, bh) * 0.05))
                    if (bx - pad) <= click_x <= (bx + bw + pad) and (by - pad) <= click_y <= (by + bh + pad):
                        containing.append(i)

                best_idx = -1
                best_dist = float('inf')
                if containing:
                    # Several people can overlap on screen -- the SMALLEST
                    # containing box is almost always the one actually
                    # clicked (a bigger box behind/around them just also
                    # happens to cover the same point).
                    best_idx = min(containing, key=lambda ci: yolo_objects[ci]['bbox'][2] * yolo_objects[ci]['bbox'][3])
                else:
                    for i, p in enumerate(yolo_objects):
                        pcx, pcy = p['center'][1], p['center'][0]
                        dist = ((click_x - pcx) ** 2 + (click_y - pcy) ** 2) ** 0.5
                        if dist < best_dist:
                            best_dist = dist
                            best_idx = i

                # Nothing actually contained the click, and the nearest
                # object is still far away -- don't silently snap to it.
                # Let this fall through to the next detector (or the
                # "click closer" message) instead of confidently landing
                # the arrow on someone on the other side of the frame.
                max_click_dist = max(h_frame, w_frame) * 0.10
                if not containing and best_idx >= 0 and best_dist > max_click_dist:
                    print(f"[OBJ-SELECT] rejected: nearest object is {best_dist:.0f}px away (limit {max_click_dist:.0f}px) — falling through")
                    best_idx = -1

                for i, p in enumerate(yolo_objects):
                    pcx, pcy = p['center'][1], p['center'][0]
                    dist = ((click_x - pcx) ** 2 + (click_y - pcy) ** 2) ** 0.5
                    cname = p.get('class_name', 'object')
                    print(f"[OBJ-SELECT]   obj[{i}] id={p.get('id','?')} class={cname} conf={p.get('conf',0):.2f} center=({pcx},{pcy}) bbox={p['bbox']} dist={dist:.1f} contains_click={i in containing}")
                if best_idx >= 0:
                    chosen = yolo_objects[best_idx]
                    # Use YOLO's own instance mask — clean, per-person, no background bleed
                    if chosen.get('raw_mask') is not None:
                        person_mask = chosen['raw_mask'].copy()
                        if person_mask.shape[:2] != (h_frame, w_frame):
                            person_mask = cv2.resize(person_mask, (w_frame, h_frame), interpolation=cv2.INTER_LINEAR)
                    else:
                        person_mask = self._make_person_bbox_mask(frame, chosen['bbox'])

                    full_bbox = chosen['bbox']
                    full_center = chosen['center']

                    item['effect_selected_person'] = chosen.get('id', 0)
                    item['effect_yolo_locked'] = True
                    self._effect_selected_person.set(chosen.get('id', 0))
                    item['effect_person_mask_template'] = person_mask
                    item['effect_selected_class'] = chosen.get('class_name', 'object')

                    template = self._get_person_appearance(frame, full_bbox)
                    if template is None:
                        # Fallback: create minimal template from bbox region
                        x, y, bw, bh = full_bbox
                        x0, y0 = max(0, x), max(0, y)
                        x1, y1 = min(w_frame, x + bw), min(h_frame, y + bh)
                        if x1 - x0 > 2 and y1 - y0 > 2:
                            region = frame[y0:y1, x0:x1]
                            hsv_obj = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
                            obj_hist = cv2.calcHist([hsv_obj], [0, 1], None, [12, 8], [0, 180, 0, 256])
                            cv2.normalize(obj_hist, obj_hist, 0, 1, cv2.NORM_MINMAX)
                            gray_obj = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
                            edges = cv2.Canny(gray_obj, 50, 150)
                            edge_template = cv2.resize(edges, (48, 80), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
                            template = {
                                'face_hist': None, 'face_embedding': None, 'face_rect': None,
                                'body_hist': obj_hist, 'edge_template': edge_template,
                                'bbox': full_bbox, 'center': full_center,
                                'size': (bw, bh), 'area': bw * bh,
                            }
                    if template is not None:
                        item['effect_person_template'] = template
                        item['effect_face_buffer'] = [template]

                    # Anchor the tracking chain here. A brand new selection
                    # discards any previous tracking history; a correction
                    # (re-click while already tracking) leaves earlier
                    # frames' positions untouched and only clears the
                    # trajectory from this frame onward.
                    frame_idx0 = self._anchor_tracking_at(item, frame, full_center, full_bbox, is_correction)

                    cname = chosen.get('class_name', 'object')
                    self.update_global_preview()
                    self._person_status_label.config(
                        text=f"{cname.title()} selected (YOLO ID:{chosen.get('id','?')}). Instance mask active.",
                        fg=C["accent3"])
                    self.status_label.config(
                        text=f"{cname.title()} selected via YOLO-seg. Instance mask active.",
                        fg=C["accent3"])
                    return

            # Fallback: MediaPipe if YOLO finds nothing
            mp_mask = self._get_mediapipe_mask(frame)
            if mp_mask is not None and mp_mask.max() > 0.01:
                binary = (mp_mask > 0.3).astype(np.uint8)
                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
                best_label = -1
                best_dist = float('inf')
                click_label = 0
                if 0 <= click_y < labels.shape[0] and 0 <= click_x < labels.shape[1]:
                    click_label = labels[click_y, click_x]
                if click_label > 0 and stats[click_label, cv2.CC_STAT_AREA] >= 500:
                    # The click pixel itself falls inside this blob -- use
                    # it directly instead of guessing from centroid distance.
                    best_label = click_label
                else:
                    for i in range(1, num_labels):
                        area = stats[i, cv2.CC_STAT_AREA]
                        if area < 500:
                            continue
                        cx, cy = centroids[i]
                        dist = ((click_x - cx) ** 2 + (click_y - cy) ** 2) ** 0.5
                        if dist < best_dist:
                            best_dist = dist
                            best_label = i
                    max_click_dist = max(h_frame, w_frame) * 0.10
                    if best_label > 0 and best_dist > max_click_dist:
                        best_label = -1
                if best_label > 0:
                    person_mask = self._color_segment_person(frame, click_x, click_y)

                    ys, xs = np.where(person_mask > 0.1)
                    if len(xs) > 0 and len(ys) > 0:
                        bx0, by0 = int(xs.min()), int(ys.min())
                        bx1, by1 = int(xs.max()), int(ys.max())
                        full_bbox = (bx0, by0, bx1 - bx0, by1 - by0)
                        full_center = (by0 + (by1 - by0) // 2, bx0 + (bx1 - bx0) // 2)
                    else:
                        full_bbox = (0, 0, w_frame, h_frame)
                        full_center = (h_frame // 2, w_frame // 2)

                    item['effect_selected_person'] = -2  # sentinel: selected via fallback (no YOLO ID)
                    item['effect_yolo_locked'] = False
                    self._effect_selected_person.set(-2)
                    item['effect_person_mask_template'] = person_mask
                    item['effect_selected_class'] = 'object'

                    template = self._get_person_appearance(frame, full_bbox)
                    if template is not None:
                        item['effect_person_template'] = template
                        item['effect_face_buffer'] = [template]

                    # Anchor the tracking chain here -- see the note in the
                    # YOLO branch above for full vs. correction behaviour.
                    frame_idx0 = self._anchor_tracking_at(item, frame, full_center, full_bbox, is_correction)

                    self.update_global_preview()
                    self._person_status_label.config(
                        text=f"Object selected! Full body outline active.",
                        fg=C["accent3"])
                    self.status_label.config(
                        text=f"Object selected. Outline rendering.",
                        fg=C["accent3"])
                    return

            # Fallback: HOG / face detection if MediaPipe fails
            persons = self._detect_all_persons(frame)
            if not persons:
                self._person_status_label.config(
                    text="No objects detected. Try clicking closer to an object.", fg=C["danger"])
                return

            containing = []
            for i, p in enumerate(persons):
                bx, by, bw, bh = p['bbox']
                pad = max(2, int(min(bw, bh) * 0.05))
                if (bx - pad) <= click_x <= (bx + bw + pad) and (by - pad) <= click_y <= (by + bh + pad):
                    containing.append(i)

            best_idx = 0
            best_dist = float('inf')
            if containing:
                best_idx = min(containing, key=lambda ci: persons[ci]['bbox'][2] * persons[ci]['bbox'][3])
            else:
                for i, p in enumerate(persons):
                    pcx, pcy = p['center'][1], p['center'][0]
                    dist = ((click_x - pcx) ** 2 + (click_y - pcy) ** 2) ** 0.5
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = i

            # This is the last detector in the chain -- if nothing actually
            # contained the click and even the nearest person is far away,
            # say so plainly instead of grabbing whoever happens to be
            # closest, however far across the frame that is.
            max_click_dist = max(h_frame, w_frame) * 0.10
            if not containing and best_dist > max_click_dist:
                self._person_status_label.config(
                    text="Nothing detected right at that spot — click closer to the center of the person/object.",
                    fg=C["danger"])
                return

            chosen = persons[best_idx]
            item['effect_selected_person'] = -2  # sentinel: selected via fallback (no YOLO ID)
            item['effect_yolo_locked'] = False
            self._effect_selected_person.set(-2)
            item['effect_selected_class'] = 'person'

            mask = self._generate_mask_from_bbox(frame, chosen['bbox'])
            if mask is not None:
                item['effect_person_mask_template'] = mask

            template = self._get_person_appearance(frame, chosen['bbox'])
            if template is not None:
                item['effect_person_template'] = template
                item['effect_face_buffer'] = [template]

            frame_idx0 = self._anchor_tracking_at(item, frame, chosen['center'], chosen['bbox'], is_correction)
            self.update_global_preview()
            bx, by, bw, bh = chosen['bbox']
            self._person_status_label.config(
                text=f"Object selected! ({bw}x{bh}px). Gold outline active.",
                fg=C["accent3"])
            if hasattr(self, '_mt_person_status'):
                self._mt_person_status.config(
                    text=f"Object tracked (ID: {item.get('effect_selected_person', -1)}). Enable Motion Track above.",
                    fg=C["accent3"])
            self.status_label.config(
                text=f"Object selected at ({bx},{by}). Outline rendering.",
                fg=C["accent3"])

        except Exception as ex:
            print("Person selection error:", ex)
            import traceback; traceback.print_exc()
            self._person_status_label.config(text="Selection failed. Try again.", fg=C["danger"])

    def _draw_selection_feedback(self, frame, bbox, label):
        """Draw a colored bounding box on the preview to show who was selected."""
        try:
            import PIL.ImageDraw, PIL.ImageFont
            h_frame, w_frame = frame.shape[:2]
            img = PIL.Image.fromarray(frame)
            pw = getattr(self, '_preview_label_w', max(self.preview_label.winfo_width(), 320))
            ph = getattr(self, '_preview_label_h', max(self.preview_label.winfo_height(), 180))
            img.thumbnail((pw, ph), PIL.Image.LANCZOS)
            disp_w, disp_h = img.size
            ox = getattr(self, '_preview_offset_x', 0)
            oy = getattr(self, '_preview_offset_y', 0)
            draw = ImageDraw.Draw(img)
            # Scale bbox from frame coords to display coords
            sx = disp_w / max(1, w_frame)
            sy = disp_h / max(1, h_frame)
            x, y, bw, bh = bbox
            dx = int(x * sx)
            dy = int(y * sy)
            dbw = int(bw * sx)
            dbh = int(bh * sy)
            for offset in range(3):
                draw.rectangle(
                    [dx - offset, dy - offset, dx + dbw + offset, dy + dbh + offset],
                    outline=(0, 255, 0))
            try:
                font = PIL.ImageFont.truetype("arial.ttf", 14)
            except Exception:
                font = PIL.ImageFont.load_default()
            try:
                bbox_text = draw.textbbox((0, 0), label, font=font)
                text_w = bbox_text[2] - bbox_text[0]
                text_h = bbox_text[3] - bbox_text[1]
            except Exception:
                text_w, text_h = len(label) * 8, 14
            draw.rectangle([dx, dy - text_h - 6, dx + text_w + 8, dy], fill=(0, 200, 0))
            draw.text((dx + 4, dy - text_h - 4), label, fill=(0, 0, 0), font=font)
            self.preview_img = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self.preview_img, text="")
        except Exception as ex:
            print("Selection feedback error:", ex)

    def _get_preview_frame(self, item):
        if item['type'] == 'image':
            try:
                img = PIL.Image.open(item['path']).convert('RGB')
                return np.array(img)
            except Exception:
                return None
        elif item['type'] == 'video':
            try:
                if item['path'] not in self._clip_cache:
                    from moviepy.editor import VideoFileClip as _VFC
                    self._clip_cache_put(item['path'], _VFC(item['path']))
                clip = self._clip_cache[item['path']]
                t = self.playhead_t.get()
                cs = float(item.get('clip_start', 0.0))
                ce = float(item.get('clip_end', 0.0))
                if ce > cs:
                    t = cs + (t % max(0.1, ce - cs))
                else:
                    t = min(t, clip.duration - 0.01)
                frame = clip.get_frame(t)
                return frame
            except Exception:
                return None
        return None

    def _update_person_buttons(self):
        for w in self._person_btn_frame.winfo_children():
            w.destroy()
        persons = self._detected_persons
        sel = self._effect_selected_person.get()
        if not persons:
            tk.Label(self._person_btn_frame, text="No persons detected", bg=C["panel"],
                     fg=C["text_dim"], font=("Segoe UI", 7)).pack(anchor="w")
            return
        for i, p in enumerate(persons):
            if 'id' in p:
                label = f"ID:{p['id']}"
            else:
                label = f"Person {i + 1}"
            is_sel = (p.get('id', i) == sel)
            bg = C["accent"] if is_sel else C["raised"]
            btn = tk.Button(self._person_btn_frame, text=label, bg=bg, fg="white", bd=0,
                           font=("Segoe UI", 7, "bold" if is_sel else "normal"),
                           command=lambda idx=i, pid=p.get('id', i): self._on_person_selected(pid))
            btn.pack(side=tk.LEFT, padx=2, pady=1)

    def _on_person_selected(self, person_id):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_selected_person'] = person_id
        has_yolo = any('id' in p for p in self._detected_persons) if self._detected_persons else False
        item['effect_yolo_locked'] = has_yolo
        self._effect_selected_person.set(person_id)
        self._update_person_buttons()
        # Store appearance template for the selected person
        t = self.playhead_t.get()
        frame_idx = int(t * 30)
        if self._detected_persons:
            if has_yolo:
                # person_id is a YOLO track ID — find matching person
                matched = None
                for p in self._detected_persons:
                    if p.get('id') == person_id:
                        matched = p
                        break
                if matched is None and self._detected_persons:
                    matched = self._detected_persons[0]
                if matched is not None:
                    self._track_person_across_frames(
                        item, frame_idx, [matched], 0)
            else:
                # person_id is an index
                if person_id < len(self._detected_persons):
                    self._track_person_across_frames(
                        item, frame_idx, self._detected_persons, person_id)
        self.update_global_preview()

    def _deselect_person(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_selected_person'] = -1
        item['effect_yolo_locked'] = False
        item['effect_tracking_keyframes'] = {}
        item['effect_person_template'] = None
        item['effect_face_buffer'] = []
        item['effect_mask_user_edited'] = False
        item['effect_selected_class'] = None
        self._effect_selected_person.set(-1)
        self._detected_persons = []
        self._update_person_buttons()
        self._person_status_label.config(text="Object deselected — auto-detect active", fg=C["text_dim"])
        if hasattr(self, '_mt_person_status'):
                self._mt_person_status.config(text="Object deselected — auto-detect active", fg=C["text_dim"])
        self.update_global_preview()

    def _toggle_outline_preview(self):
        self._show_outline_var.set(not self._show_outline_var.get())
        if self._show_outline_var.get():
            self._outline_toggle_btn.config(text="Hide Outline (Preview Mask)", bg="#4a148c")
        else:
            self._outline_toggle_btn.config(text="Show Outline (Preview Mask)", bg="#1a237e")
        self.update_global_preview()

    def _toggle_mask_edit_mode(self):
        if self.selected_idx is None:
            return
        self._mask_edit_active = not self._mask_edit_active
        if self._mask_edit_active:
            item = self.media_queue[self.selected_idx]
            # Use transformed frame (matches preview) so mask aligns correctly
            frame = self._get_transformed_frame(item)
            if frame is None:
                # Fallback to raw frame
                frame = self._get_preview_frame(item)
            if frame is None:
                self._mask_edit_active = False
                return
            h_raw, w_raw = frame.shape[:2]

            # Compute display resolution (same as update_global_preview)
            is_mobile = (self.format_var.get() == "mobile")
            target_w = 540 if is_mobile else 960
            target_h = 960 if is_mobile else 540

            if item.get('effect_mask_painting') is None:
                # Always generate mask from the CURRENT frame so outline
                # matches the displayed frame (not the stale selection-time frame)
                selected_id = int(item.get('effect_selected_person', -1))
                if selected_id >= 0 or selected_id == -2:
                    mp_mask = self._get_selected_person_mask(frame, item)
                else:
                    mp_mask = self._get_mediapipe_mask(frame)
                if mp_mask is not None and mp_mask.max() > 0:
                    mp_mask = cv2.resize(mp_mask, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                    item['effect_mask_painting'] = mp_mask.copy()
                else:
                    item['effect_mask_painting'] = np.zeros((target_h, target_w), dtype=np.float32)
            if item.get('effect_drawn_mask') is None:
                item['effect_drawn_mask'] = np.zeros((target_h, target_w), dtype=np.float32)
            # Cache the base person mask at display resolution for stable editing preview
            painting = item.get('effect_mask_painting')
            if painting is not None:
                item['effect_editing_base_mask'] = painting.copy()
            else:
                item['effect_editing_base_mask'] = np.ones((target_h, target_w), dtype=np.float32)

            # Ensure mask is at display resolution (re-init if wrong size)
            painting = item.get('effect_mask_painting')
            if painting is not None:
                ph, pw = painting.shape[:2]
                if ph != target_h or pw != target_w:
                    painting = cv2.resize(painting, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                    item['effect_mask_painting'] = painting

            h, w = target_h, target_w
            self._mask_edit_btn.config(text="Stop Editing Outline", bg="#b71c1c")
            self._show_outline_var.set(True)
            self._outline_toggle_btn.config(text="Hide Outline (Preview Mask)", bg="#4a148c")
            pw = max(self.preview_label.winfo_width(), 320)
            ph = max(self.preview_label.winfo_height(), 180)
            tmp_img = PIL.Image.new("RGB", (w, h))
            tmp_img.thumbnail((pw, ph), PIL.Image.LANCZOS)
            disp_w, disp_h = tmp_img.size
            self._mask_offset_x = (pw - disp_w) // 2
            self._mask_offset_y = (ph - disp_h) // 2
            self._mask_scale_x = w / max(1, disp_w)
            self._mask_scale_y = h / max(1, disp_h)
            self._mask_frame_w = w
            self._mask_frame_h = h
            self.preview_label.config(cursor="circle")
            self.preview_label.bind("<ButtonPress-1>", self._on_mask_paint_start)
            self.preview_label.bind("<B1-Motion>", self._on_mask_paint_drag)
            self.preview_label.bind("<ButtonRelease-1>", self._on_mask_paint_end)
            self.update_global_preview()
            self.status_label.config(text="Editing outline mask — drag on preview to erase/draw", fg=C["accent4"])
        else:
            self._mask_edit_btn.config(text="Start Editing Outline", bg="#e65100")
            self.preview_label.config(cursor="")
            self.preview_label.unbind("<ButtonPress-1>")
            self.preview_label.unbind("<B1-Motion>")
            self.preview_label.unbind("<ButtonRelease-1>")
            self._show_outline_var.set(False)
            self._outline_toggle_btn.config(text="Show Outline (Preview Mask)", bg="#1a237e")
            self.update_global_preview()
            self.status_label.config(text="Outline mask editing stopped", fg=C["accent3"])

    def _on_mask_paint_start(self, event):
        self._mask_last_x = event.x
        self._mask_last_y = event.y
        self._on_mask_paint_draw(event.x, event.y)

    def _on_mask_paint_drag(self, event):
        self._on_mask_paint_draw(event.x, event.y)

    def _on_mask_paint_draw(self, ex, ey):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        mask = item.get('effect_mask_painting')
        if mask is None:
            return
        item['effect_mask_user_edited'] = True
        h, w = mask.shape[:2]
        disp_w = getattr(self, '_preview_disp_w', None)
        disp_h = getattr(self, '_preview_disp_h', None)
        ox = getattr(self, '_preview_offset_x', 0)
        oy = getattr(self, '_preview_offset_y', 0)
        if disp_w is None or disp_h is None:
            pw = max(self.preview_label.winfo_width(), 320)
            ph = max(self.preview_label.winfo_height(), 180)
            img_aspect = w / max(1, h)
            if pw / max(1, ph) > img_aspect:
                disp_h = ph
                disp_w = int(ph * img_aspect)
            else:
                disp_w = pw
                disp_h = int(pw / img_aspect)
            disp_w = max(1, disp_w)
            disp_h = max(1, disp_h)
            ox = (pw - disp_w) // 2
            oy = (ph - disp_h) // 2
        sx = w / max(1, disp_w)
        sy = h / max(1, disp_h)
        cx = int((ex - ox) * sx)
        cy = int((ey - oy) * sy)
        radius = self._mask_brush_size.get()
        erase = self._mask_erase_mode.get() == "erase"
        tip_r = max(2, radius // 6)
        if erase:
            cv2.circle(mask, (cx, cy), tip_r, 0.0, -1)
            if hasattr(self, '_mask_last_x'):
                lx = int((self._mask_last_x - ox) * sx)
                ly = int((self._mask_last_y - oy) * sy)
                cv2.line(mask, (lx, ly), (cx, cy), 0.0, max(1, tip_r))
            drawn = item.get('effect_drawn_mask')
            if drawn is not None and drawn.shape[:2] == (h, w):
                cv2.circle(drawn, (cx, cy), tip_r, 0.0, -1)
                if hasattr(self, '_mask_last_x'):
                    lx = int((self._mask_last_x - ox) * sx)
                    ly = int((self._mask_last_y - oy) * sy)
                    cv2.line(drawn, (lx, ly), (cx, cy), 0.0, max(1, tip_r))
        else:
            cv2.circle(mask, (cx, cy), tip_r, 1.0, -1)
            if hasattr(self, '_mask_last_x'):
                lx = int((self._mask_last_x - ox) * sx)
                ly = int((self._mask_last_y - oy) * sy)
                cv2.line(mask, (lx, ly), (cx, cy), 1.0, max(1, tip_r))
            drawn = item.get('effect_drawn_mask')
            if drawn is not None and drawn.shape[:2] == (h, w):
                cv2.circle(drawn, (cx, cy), tip_r, 1.0, -1)
                if hasattr(self, '_mask_last_x'):
                    lx = int((self._mask_last_x - ox) * sx)
                    ly = int((self._mask_last_y - oy) * sy)
                    cv2.line(drawn, (lx, ly), (cx, cy), 1.0, max(1, tip_r))
        self._mask_last_x = ex
        self._mask_last_y = ey
        self._debounced_preview(interactive=True)

    def _on_mask_paint_end(self, event):
        pass

    def _clear_mask_painting(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_mask_painting'] = None
        item['effect_drawn_mask'] = None
        item['effect_mask_user_edited'] = False
        self.update_global_preview()
        self.status_label.config(text="Outline mask cleared", fg=C["accent3"])
