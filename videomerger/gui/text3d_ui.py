"""3D-text placement, transform handles and auto-tracking UI.

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


class Text3DUIMixin:
    """3D-text placement, transform handles and auto-tracking UI."""

    def _default_3d_text_quad(self):
        """A gentle ground-plane trapezoid: narrower/higher at the back,
        wider/lower at the front — a reasonable starting point that the
        user reshapes by dragging corners to match their footage."""
        return [[0.32, 0.40], [0.70, 0.40], [0.82, 0.62], [0.20, 0.62]]

    def _get_3d_text_quad(self, item):
        """Returns the item's 4-point quad (TL, TR, BR, BL) as fractions
        of the frame, migrating from the old single-point placement if
        that's all that's stored, else falling back to a default quad."""
        q = item.get('3d_text_quad')
        if q and len(q) == 4:
            return [list(p) for p in q]
        cx = item.get('3d_text_pos_x', 0.5)
        cy = item.get('3d_text_pos_y', 0.5)
        if '3d_text_pos_x' in item or '3d_text_pos_y' in item:
            fs = item.get('3d_text_font_size', 0.14)
            hw, hh = fs * 1.6, fs * 0.6
            return [[cx - hw * 0.85, cy - hh], [cx + hw * 0.85, cy - hh],
                    [cx + hw, cy + hh], [cx - hw, cy + hh]]
        return self._default_3d_text_quad()

    def _3d_text_quad_disp_pts(self, quad, disp_w, disp_h):
        return [(p[0] * disp_w, p[1] * disp_h) for p in quad]

    def _3d_text_rotate_handle_disp(self, corner_pts_disp):
        cx = sum(p[0] for p in corner_pts_disp) / 4.0
        cy = sum(p[1] for p in corner_pts_disp) / 4.0
        top_mid = ((corner_pts_disp[0][0] + corner_pts_disp[1][0]) / 2.0,
                   (corner_pts_disp[0][1] + corner_pts_disp[1][1]) / 2.0)
        dx, dy = top_mid[0] - cx, top_mid[1] - cy
        dist = max(1e-4, math.hypot(dx, dy))
        return (top_mid[0] + dx / dist * self._3D_TEXT_ROT_HANDLE_LEN,
                top_mid[1] + dy / dist * self._3D_TEXT_ROT_HANDLE_LEN), top_mid, (cx, cy)

    def _3d_text_edge_midpoints_disp(self, corner_pts_disp):
        mids = {}
        for name, (idxs, _axis) in self._3D_TEXT_EDGES.items():
            i, j = idxs
            mids[name] = ((corner_pts_disp[i][0] + corner_pts_disp[j][0]) / 2.0,
                          (corner_pts_disp[i][1] + corner_pts_disp[j][1]) / 2.0)
        return mids

    @staticmethod
    def _point_in_quad(x, y, pts):
        inside = False
        n = len(pts)
        j = n - 1
        for i in range(n):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-9) + xi):
                inside = not inside
            j = i
        return inside

    def _toggle_3d_text_drag(self):
        if self.selected_idx is None:
            return messagebox.showwarning("3D Text", "Select a clip first.")
        item = self.media_queue[self.selected_idx]
        if item['type'] not in ('video', 'image', 'placeholder', 'title'):
            return
        if not item.get('effect_3d_text_enabled', False):
            self._3d_text_enabled.set(True)
            item['effect_3d_text_enabled'] = True
        if item.get('3d_text_quad') is None:
            item['3d_text_quad'] = self._get_3d_text_quad(item)
        self._3d_text_place_active = not self._3d_text_place_active
        if self._3d_text_place_active:
            self._3d_text_place_btn.config(text="Stop Editing", bg="#b71c1c")
            self._3d_text_status.config(
                text="Move=inside • Resize=corner • Tilt/wall=yellow dot • Rotate=red dot", fg=C["accent"])
            self.preview_label.config(cursor="fleur")
            self.preview_label.bind("<ButtonPress-1>", self._on_3d_text_transform_start)
            self.preview_label.bind("<B1-Motion>", self._on_3d_text_transform_move)
            self.preview_label.bind("<ButtonRelease-1>", self._on_3d_text_transform_end)
            self._debounced_preview(interactive=True)
        else:
            self._3d_text_place_btn.config(text="Edit Text on Preview", bg=C["accent"])
            self._3d_text_status.config(
                text="Drag inside=move • corner=resize • yellow dot=tilt/wall • red dot=rotate",
                fg=C["text_dim"])
            self.preview_label.config(cursor="")
            self.preview_label.unbind("<ButtonPress-1>")
            self.preview_label.unbind("<B1-Motion>")
            self.preview_label.unbind("<ButtonRelease-1>")
            self.update_global_preview()

    def _on_3d_text_transform_start(self, event):
        if not self._3d_text_place_active or self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        disp_w = getattr(self, '_preview_disp_w', None)
        disp_h = getattr(self, '_preview_disp_h', None)
        if not disp_w or not disp_h:
            return
        ox = getattr(self, '_preview_offset_x', 0)
        oy = getattr(self, '_preview_offset_y', 0)
        tx, ty = event.x - ox, event.y - oy

        quad = self._get_3d_text_quad(item)
        corner_pts = self._3d_text_quad_disp_pts(quad, disp_w, disp_h)
        rot_handle, _, centroid = self._3d_text_rotate_handle_disp(corner_pts)
        edge_mids = self._3d_text_edge_midpoints_disp(corner_pts)

        mode, corner_idx, edge_name = None, None, None
        r = self._3D_TEXT_HANDLE_R
        if (tx - rot_handle[0]) ** 2 + (ty - rot_handle[1]) ** 2 <= (r + 4) ** 2:
            mode = 'rotate'
        else:
            for i, (hx, hy) in enumerate(corner_pts):
                if (tx - hx) ** 2 + (ty - hy) ** 2 <= r ** 2:
                    mode, corner_idx = 'corner', i
                    break
        if mode is None:
            for name, (mx, my) in edge_mids.items():
                if (tx - mx) ** 2 + (ty - my) ** 2 <= r ** 2:
                    mode, edge_name = 'edge', name
                    break
        if mode is None:
            if self._point_in_quad(tx, ty, corner_pts):
                mode = 'move'
            else:
                return  # clicked outside the text — ignore, don't start a drag

        self._3d_text_dragging = True
        self._3d_text_drag_mode = mode
        self._3d_text_drag_corner_idx = corner_idx
        self._3d_text_drag_edge_name = edge_name
        self._3d_text_drag_start_evt = (event.x, event.y)
        self._3d_text_drag_start_quad = quad
        self._3d_text_drag_start_centroid_frac = (centroid[0] / disp_w, centroid[1] / disp_h)
        self._3d_text_drag_start_angle = math.atan2(ty - centroid[1], tx - centroid[0])

    def _on_3d_text_transform_move(self, event):
        if not getattr(self, '_3d_text_dragging', False) or self.selected_idx is None:
            return
        disp_w = getattr(self, '_preview_disp_w', None)
        disp_h = getattr(self, '_preview_disp_h', None)
        if not disp_w or not disp_h:
            return
        ox = getattr(self, '_preview_offset_x', 0)
        oy = getattr(self, '_preview_offset_y', 0)
        quad0 = self._3d_text_drag_start_quad
        mode = self._3d_text_drag_mode

        if mode == 'move':
            dx = (event.x - self._3d_text_drag_start_evt[0]) / disp_w
            dy = (event.y - self._3d_text_drag_start_evt[1]) / disp_h
            new_quad = [[p[0] + dx, p[1] + dy] for p in quad0]

        elif mode == 'corner':
            nx = (event.x - ox) / disp_w
            ny = (event.y - oy) / disp_h
            new_quad = [list(p) for p in quad0]
            new_quad[self._3d_text_drag_corner_idx] = [nx, ny]

        elif mode == 'edge':
            # One clean, axis-locked drag per edge: top/bottom edges only
            # tilt (move vertically), left/right edges only angle the text
            # onto a side wall (move horizontally) — so you can't
            # accidentally warp the other axis while you're just trying
            # to tilt it.
            idxs, axis = self._3D_TEXT_EDGES[self._3d_text_drag_edge_name]
            new_quad = [list(p) for p in quad0]
            if axis == 'y':
                dy = (event.y - self._3d_text_drag_start_evt[1]) / disp_h
                for i in idxs:
                    new_quad[i][1] = quad0[i][1] + dy
            else:
                dx = (event.x - self._3d_text_drag_start_evt[0]) / disp_w
                for i in idxs:
                    new_quad[i][0] = quad0[i][0] + dx

        elif mode == 'rotate':
            cx_f, cy_f = self._3d_text_drag_start_centroid_frac
            cx, cy = cx_f * disp_w, cy_f * disp_h
            tx, ty = event.x - ox, event.y - oy
            ang = math.atan2(ty - cy, tx - cx)
            dtheta = ang - self._3d_text_drag_start_angle
            cos_a, sin_a = math.cos(dtheta), math.sin(dtheta)
            new_quad = []
            for p in quad0:
                px, py = p[0] * disp_w - cx, p[1] * disp_h - cy
                rx = px * cos_a - py * sin_a
                ry = px * sin_a + py * cos_a
                new_quad.append([(rx + cx) / disp_w, (ry + cy) / disp_h])
        else:
            return

        item = self.media_queue[self.selected_idx]
        item['3d_text_quad'] = new_quad
        self._debounced_preview(interactive=True)

    def _on_3d_text_transform_end(self, event):
        if not getattr(self, '_3d_text_dragging', False):
            return
        self._3d_text_dragging = False
        label = {'move': 'Moved', 'corner': 'Resized', 'edge': 'Tilted', 'rotate': 'Rotated'}.get(
            self._3d_text_drag_mode, 'Updated')
        self._3d_text_drag_mode = None
        self._3d_text_status.config(text=f"{label} ✓  —  drag again to keep adjusting", fg=C["accent3"])
        self.update_global_preview()

    def _draw_3d_text_handles(self, img, item):
        """Draws the quad outline plus its move/corner/edge/rotate handles
        onto the (still full frame-resolution) preview image, so the user
        can see exactly what they're about to drag."""
        w, h = img.size
        quad = self._get_3d_text_quad(item)
        pts = [(p[0] * w, p[1] * h) for p in quad]
        rot_handle, top_mid, centroid = self._3d_text_rotate_handle_disp(pts)
        edge_mids = self._3d_text_edge_midpoints_disp(pts)

        out = img.convert("RGB").copy()
        draw = ImageDraw.Draw(out)

        draw.line(pts + [pts[0]], fill=(0, 200, 255), width=2)
        draw.line([top_mid, rot_handle], fill=(0, 200, 255), width=2)

        hr = 8
        for (hx, hy) in pts:
            draw.rectangle([hx - hr, hy - hr, hx + hr, hy + hr],
                            fill=(0, 200, 255), outline=(255, 255, 255), width=2)

        er = 7
        for (ex, ey) in edge_mids.values():
            draw.ellipse([ex - er, ey - er, ex + er, ey + er],
                          fill=(255, 210, 0), outline=(255, 255, 255), width=2)

        rr = 9
        draw.ellipse([rot_handle[0] - rr, rot_handle[1] - rr, rot_handle[0] + rr, rot_handle[1] + rr],
                      fill=(255, 60, 60), outline=(255, 255, 255), width=2)

        return out

    def _3d_text_fit_mapping(self, clip_w, clip_h, is_mobile, smart_fill, scale_val):
        """Pure-math mapping between (a) fractions of the composed output
        canvas — the space the quad is stored/edited in — and (b) pixel
        coordinates of the raw source video frame — the space optical flow
        tracking runs in. Mirrors the fit/crop math in update_global_preview
        so a quad placed on the preview lines up with the real footage."""
        target_w = 1080 if is_mobile else 1920
        target_h = 1920 if is_mobile else 1080
        if smart_fill:
            base_sf = max(target_w / clip_w, target_h / clip_h) * scale_val
        else:
            base_sf = min(target_w / clip_w, target_h / clip_h) * scale_val
        base_sf = max(1e-6, base_sf)
        new_w, new_h = clip_w * base_sf, clip_h * base_sf
        if smart_fill:
            off_x, off_y = (new_w - target_w) / 2.0, (new_h - target_h) / 2.0

            def frac_to_raw(fx, fy):
                return (fx * target_w + off_x) / base_sf, (fy * target_h + off_y) / base_sf

            def raw_to_frac(rx, ry):
                return (rx * base_sf - off_x) / target_w, (ry * base_sf - off_y) / target_h
        else:
            off_x, off_y = (target_w - new_w) / 2.0, (target_h - new_h) / 2.0

            def frac_to_raw(fx, fy):
                return (fx * target_w - off_x) / base_sf, (fy * target_h - off_y) / base_sf

            def raw_to_frac(rx, ry):
                return (rx * base_sf + off_x) / target_w, (ry * base_sf + off_y) / target_h
        return frac_to_raw, raw_to_frac

    def _get_3d_text_quad_at(self, item, t):
        """The quad to render at local time t: the live AR-tracked quad if
        this clip has been auto-tracked (and t is within the tracked
        range), otherwise the plain static anchor quad. Returns None when
        tracking has run out (camera has moved past the anchored point) —
        the caller should render nothing in that case."""
        if (getattr(self, '_3d_text_place_active', False) and self.selected_idx is not None
                and self.selected_idx < len(self.media_queue) and self.media_queue[self.selected_idx] is item):
            return self._get_3d_text_quad(item)  # editing always shows/edits the raw anchor

        track = item.get('3d_text_track')
        if not track:
            return self._get_3d_text_quad(item)
        quads = track.get('quads') or {}
        if not quads:
            return self._get_3d_text_quad(item)

        anchor_t = track.get('anchor_t', 0.0)
        dt = track.get('local_dt_per_step') or (1.0 / max(1.0, track.get('fps', 30.0)))
        rel = (t - anchor_t) / max(1e-6, dt)
        if rel < -1.0:
            return self._get_3d_text_quad(item)  # before the anchor point — not tracked yet, show it static

        int_keys = sorted(int(k) for k in quads.keys())
        max_step = int_keys[-1]
        if rel > max_step + 1.0:
            return None  # tracking ran out here — the camera has moved past it

        k0 = max(0, min(max_step, int(math.floor(rel))))
        while k0 not in quads and k0 > 0:
            k0 -= 1
        k1 = k0 + 1 if (k0 + 1) in quads else k0
        alpha = max(0.0, min(1.0, rel - k0)) if k1 != k0 else 0.0

        mp = track.get('map_params', {})
        frac_to_raw, raw_to_frac = self._3d_text_fit_mapping(
            mp.get('clip_w', 1920), mp.get('clip_h', 1080), mp.get('is_mobile', False),
            mp.get('smart_fill', False), mp.get('scale_val', 1.0))

        q0 = np.float32(quads[k0] if k0 in quads else quads[str(k0)])
        if k1 == k0:
            q = q0
        else:
            q1 = np.float32(quads[k1] if k1 in quads else quads[str(k1)])
            q = q0 * (1.0 - alpha) + q1 * alpha

        # Defensive second layer: even though bad fits are rejected/smoothed
        # out at tracking time, reject a flipped/self-intersecting/degenerate
        # quad here too rather than ever render one.
        anchor_quad = self._get_3d_text_quad(item)
        anchor_raw = np.float32([frac_to_raw(p[0], p[1]) for p in anchor_quad])
        ref_area = abs(self._3d_text_quad_signed_area(anchor_raw))
        ref_sign = self._3d_text_quad_signed_area(anchor_raw) > 0
        area = self._3d_text_quad_signed_area(q)
        if (not np.all(np.isfinite(q))
                or abs(area) < 1.0
                or (area > 0) != ref_sign
                or not self._3d_text_quad_is_convex(q)
                or abs(area) / max(1e-6, ref_area) > 20.0
                or abs(area) / max(1e-6, ref_area) < 1.0 / 20.0):
            return None

        return [list(raw_to_frac(px, py)) for px, py in q]

    def _start_3d_text_autotrack(self):
        if self.selected_idx is None:
            return messagebox.showwarning("AR Tracking", "Select a clip first.")
        item = self.media_queue[self.selected_idx]
        if item['type'] != 'video' or not item.get('path'):
            return messagebox.showwarning("AR Tracking", "Auto-tracking works on video clips only.")
        if not item.get('effect_3d_text_enabled', False):
            return messagebox.showwarning("AR Tracking", "Enable 3D Text and place it on the preview first.")
        if item.get('ken_burns_enabled', False):
            return messagebox.showwarning(
                "AR Tracking",
                "Turn off Ken Burns Pan & Zoom on this clip first — auto-tracking follows the "
                "camera's real motion, so the two can't be used together.")
        if item.get('rotation', 0) or item.get('flip_h', False) or item.get('flip_v', False):
            return messagebox.showwarning(
                "AR Tracking", "Auto-tracking doesn't support rotated or flipped clips yet.")

        anchor_t = self.playhead_t.get()
        anchor_quad = self._get_3d_text_quad(item)
        end_limit = None
        if not item.get('3d_text_full_clip', True):
            end_limit = float(item.get('3d_text_end', anchor_t + 10.0))
        clip_dur = self._item_duration(item)
        clip_start = float(item.get('clip_start', 0.0))
        speed = max(0.1, float(item.get('speed', 1.0)))
        is_mobile = (self.format_var.get() == "mobile")
        smart_fill = self.smart_fill_var.get()
        scale_val = item.get('scale', 1.0)

        if hasattr(self, '_3d_text_track_status'):
            self._3d_text_track_status.config(text="Tracking… 0%", fg=C["accent"])
        if hasattr(self, '_3d_text_track_btn'):
            self._3d_text_track_btn.config(state=tk.DISABLED)

        threading.Thread(
            target=self._run_3d_text_autotrack,
            args=(item, item['path'], anchor_t, anchor_quad, end_limit, clip_dur,
                  clip_start, speed, smart_fill, scale_val, is_mobile),
            daemon=True
        ).start()

    @staticmethod
    def _3d_text_quad_signed_area(pts):
        x, y = pts[:, 0], pts[:, 1]
        return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))

    @staticmethod
    def _3d_text_quad_is_convex(pts):
        n = len(pts)
        sign = None
        for i in range(n):
            p0, p1, p2 = pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
            v1, v2 = p1 - p0, p2 - p1
            cross = v1[0] * v2[1] - v1[1] * v2[0]
            if abs(cross) < 1e-6:
                continue
            s = cross > 0
            if sign is None:
                sign = s
            elif s != sign:
                return False
        return True

    def _3d_text_homography_is_sane(self, H, anchor_pts, ref_area, ref_sign):
        """Rejects homographies that would produce visual garbage: a
        self-intersecting quad, a mirror-image reflection, or one whose
        size relative to the original placement is wildly implausible.
        RANSAC can return a "successful" fit (enough inliers) that is still
        geometrically nonsensical for real camera motion — this is what
        catches that instead of rendering the broken result. Note a plain
        180° rotation does NOT flip the sign checked here (rotations are
        orientation-preserving) — that case is caught separately, frame to
        frame, via the edge-angle jump check in the tracking loop.
        Cumulative growth vs. the anchor is allowed to be large (up to 20x)
        since the whole point is the text growing a lot as the camera
        closes in — this only rejects truly degenerate fits."""
        try:
            warped = cv2.perspectiveTransform(anchor_pts.reshape(-1, 1, 2), H).reshape(-1, 2)
        except Exception:
            return False, None, None, None
        if not np.all(np.isfinite(warped)):
            return False, None, None, None
        area = self._3d_text_quad_signed_area(warped)
        if abs(area) < 1.0:
            return False, None, None, None
        if (area > 0) != ref_sign:
            return False, None, None, None  # mirror-image reflection — not real camera motion
        if not self._3d_text_quad_is_convex(warped):
            return False, None, None, None
        if abs(area) / max(1e-6, ref_area) > 20.0 or abs(area) / max(1e-6, ref_area) < 1.0 / 20.0:
            return False, None, None, None  # implausible vs. the original placement size
        edge = warped[1] - warped[0]
        angle = math.atan2(edge[1], edge[0])
        return True, area, angle, warped

    def _3d_text_smooth_track(self, quad_seq, window=9):
        """quad_seq: (n,4,2) array of tracked quad corners, one per step,
        with NO gaps (dense_fill handles that before calling this).
        Optical-flow-derived homographies are independently estimated each
        frame from noisy point correspondences, so even smooth real camera
        motion comes out slightly jittery step to step. A short temporal
        Gaussian smoothing pass removes that jitter while preserving the
        overall approach/pass-by trend, since that trend is much slower
        than the jitter itself."""
        n = quad_seq.shape[0]
        if n < 5:
            return quad_seq
        window = min(window, n - (1 - n % 2))  # keep it odd and <= n
        window = max(3, window if window % 2 == 1 else window - 1)
        sigma = window / 4.0
        xs = np.arange(window) - window // 2
        kernel = np.exp(-0.5 * (xs / sigma) ** 2)
        kernel /= kernel.sum()
        flat = quad_seq.reshape(n, 8).astype(np.float64)
        pad = window // 2
        padded = np.pad(flat, ((pad, pad), (0, 0)), mode='edge')
        smoothed = np.empty_like(flat)
        for c in range(8):
            smoothed[:, c] = np.convolve(padded[:, c], kernel, mode='valid')
        return smoothed.reshape(n, 4, 2)

    def _run_3d_text_autotrack(self, item, path, anchor_t, anchor_quad, end_limit, clip_dur,
                                clip_start, speed, smart_fill, scale_val, is_mobile):
        cap = None
        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                self.root.after(0, self._on_3d_text_autotrack_error, item, "Couldn't open the video file.")
                return
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            clip_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            clip_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if clip_w <= 0 or clip_h <= 0:
                self.root.after(0, self._on_3d_text_autotrack_error, item, "Couldn't read the video's dimensions.")
                return

            frac_to_raw, _raw_to_frac = self._3d_text_fit_mapping(clip_w, clip_h, is_mobile, smart_fill, scale_val)
            anchor_raw = np.float32([frac_to_raw(p[0], p[1]) for p in anchor_quad])
            ref_area = abs(self._3d_text_quad_signed_area(anchor_raw))
            ref_sign = self._3d_text_quad_signed_area(anchor_raw) > 0
            prev_area = ref_area
            ref_edge = anchor_raw[1] - anchor_raw[0]
            prev_angle = math.atan2(ref_edge[1], ref_edge[0])

            anchor_raw_t = clip_start + anchor_t * speed
            anchor_frame_idx = int(round(anchor_raw_t * fps))
            max_local_t = min(clip_dur, end_limit) if end_limit else clip_dur
            max_raw_t = clip_start + max_local_t * speed
            max_frame_idx = int(round(max_raw_t * fps))
            max_frame_idx = min(max_frame_idx, anchor_frame_idx + int(fps * 60))  # hard cap: 60s of footage
            local_dt_per_step = (1.0 / fps) / speed

            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, anchor_frame_idx))
            ok, frame0 = cap.read()
            if not ok:
                self.root.after(0, self._on_3d_text_autotrack_error, item, "Couldn't read the starting frame.")
                return
            gray0 = cv2.cvtColor(frame0, cv2.COLOR_BGR2GRAY)

            # Track features from the local area the text sits on/near (more
            # robust than the whole frame — follows that surface specifically).
            xs, ys = anchor_raw[:, 0], anchor_raw[:, 1]
            mx, my = (xs.max() - xs.min()) * 0.6, (ys.max() - ys.min()) * 0.6
            x0, x1 = max(0, xs.min() - mx), min(clip_w, xs.max() + mx)
            y0, y1 = max(0, ys.min() - my), min(clip_h, ys.max() + my)
            roi_mask = np.zeros((clip_h, clip_w), dtype=np.uint8)
            roi_mask[int(y0):int(y1), int(x0):int(x1)] = 255

            pts0 = cv2.goodFeaturesToTrack(gray0, maxCorners=200, qualityLevel=0.01,
                                            minDistance=7, mask=roi_mask, blockSize=7)
            if pts0 is None or len(pts0) < 8:
                self.root.after(0, self._on_3d_text_autotrack_error, item,
                                 "Not enough visual detail there to track — try a spot with more texture.")
                return

            lk_params = dict(winSize=(21, 21), maxLevel=3,
                              criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))

            raw_quads = {0: anchor_raw.copy()}
            anchor_pts = pts0
            prev_pts = pts0
            prev_gray = gray0
            last_good_step = 0
            last_good_H = np.eye(3, dtype=np.float32)
            consecutive_bad = 0
            # Tolerate a run of shaky/noisy frames before giving up — a single
            # bad optical-flow or RANSAC fit shouldn't kill the whole track;
            # only genuinely losing the surface (e.g. camera turns away) should.
            MAX_CONSECUTIVE_BAD = 12
            total_steps = max(1, max_frame_idx - anchor_frame_idx)

            for step in range(1, total_steps + 1):
                ok, frame = cap.read()
                if not ok:
                    break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                new_pts, status, _err = cv2.calcOpticalFlowPyrLK(prev_gray, gray, prev_pts, None, **lk_params)
                good_new = good_anchor = None
                if new_pts is not None and status is not None:
                    status = status.reshape(-1)
                    gn = new_pts[status == 1]
                    ga = anchor_pts[status == 1]
                    if len(gn) >= 8:
                        good_new, good_anchor = gn, ga

                if good_new is None:
                    # Flow failed or too few points survived — try to recover
                    # by detecting fresh features and re-anchoring them via
                    # the last known-good transform, rather than giving up.
                    fresh = cv2.goodFeaturesToTrack(gray, maxCorners=200, qualityLevel=0.01,
                                                     minDistance=7, mask=roi_mask, blockSize=7)
                    if fresh is not None and len(fresh) >= 8:
                        Hinv = np.linalg.inv(last_good_H)
                        good_new = fresh
                        good_anchor = cv2.perspectiveTransform(fresh, Hinv)
                    else:
                        consecutive_bad += 1
                        prev_gray = gray
                        if consecutive_bad >= MAX_CONSECUTIVE_BAD:
                            break
                        continue

                H, inliers = cv2.findHomography(good_anchor, good_new, cv2.RANSAC, 4.0)
                step_recorded = False
                if H is not None and inliers is not None and int(inliers.sum()) >= 8:
                    is_sane, area, angle, warped = self._3d_text_homography_is_sane(H, anchor_raw, ref_area, ref_sign)
                    if is_sane:
                        step_ratio = area / max(1e-6, prev_area)
                        dtheta = (angle - prev_angle + math.pi) % (2 * math.pi) - math.pi
                        # Generous per-frame bounds — real "flying toward it" motion
                        # can grow the quad fast; this mainly rejects wild jumps
                        # (a completely different/bad match) or a flipped fit.
                        if (1.0 / 4.0) <= step_ratio <= 4.0 and abs(dtheta) <= math.radians(45):
                            raw_quads[step] = warped
                            last_good_step = step
                            last_good_H = H
                            prev_area = area
                            prev_angle = angle
                            step_recorded = True

                consecutive_bad = 0 if step_recorded else consecutive_bad + 1

                # Point tracking itself keeps going even through a frame whose
                # *homography* we didn't trust — an isolated bad fit shouldn't
                # stop the underlying feature tracking from recovering next frame.
                anchor_pts = good_anchor
                prev_pts = good_new
                prev_gray = gray

                if consecutive_bad >= MAX_CONSECUTIVE_BAD:
                    break

                if len(prev_pts) < 40:
                    fresh = cv2.goodFeaturesToTrack(gray, maxCorners=200, qualityLevel=0.01,
                                                     minDistance=7, mask=roi_mask, blockSize=7)
                    if fresh is not None:
                        Hinv = np.linalg.inv(last_good_H)
                        fresh_anchor = cv2.perspectiveTransform(fresh, Hinv)
                        prev_pts = np.concatenate([prev_pts, fresh], axis=0)
                        anchor_pts = np.concatenate([anchor_pts, fresh_anchor.astype(np.float32)], axis=0)

                if step % 10 == 0:
                    pct = int(100 * step / total_steps)
                    self.root.after(0, self._on_3d_text_autotrack_progress, pct)

            if last_good_step < 3:
                self.root.after(0, self._on_3d_text_autotrack_error, item,
                                 "Lost tracking almost immediately — try a spot with more visual detail.")
                return

            # Fill any skipped steps by interpolating between the nearest
            # recorded ones, then smooth the whole sequence to remove the
            # frame-to-frame jitter inherent to independently-estimated
            # optical-flow homographies (the "shaking" you'd otherwise see).
            recorded_steps = sorted(raw_quads.keys())
            dense_steps = list(range(0, last_good_step + 1))
            dense_quads = []
            for s in dense_steps:
                if s in raw_quads:
                    dense_quads.append(raw_quads[s])
                else:
                    lo = max((k for k in recorded_steps if k <= s), default=recorded_steps[0])
                    hi = min((k for k in recorded_steps if k >= s), default=recorded_steps[-1])
                    if hi == lo:
                        dense_quads.append(raw_quads[lo])
                    else:
                        a = (s - lo) / float(hi - lo)
                        dense_quads.append(raw_quads[lo] * (1.0 - a) + raw_quads[hi] * a)
            smoothed = self._3d_text_smooth_track(np.array(dense_quads))
            quads_by_step = {dense_steps[i]: smoothed[i].tolist() for i in range(len(dense_steps))}

            track = {
                'anchor_t': anchor_t,
                'fps': float(fps),
                'local_dt_per_step': local_dt_per_step,
                'quads': quads_by_step,
                'tracked_until_t': anchor_t + last_good_step * local_dt_per_step,
                'map_params': {'clip_w': clip_w, 'clip_h': clip_h, 'is_mobile': is_mobile,
                               'smart_fill': smart_fill, 'scale_val': scale_val},
            }
            self.root.after(0, self._on_3d_text_autotrack_done, item, track)
        except Exception as ex:
            traceback.print_exc()
            self.root.after(0, self._on_3d_text_autotrack_error, item, f"Tracking failed: {ex}")
        finally:
            if cap is not None:
                cap.release()

    def _on_3d_text_autotrack_progress(self, pct):
        if hasattr(self, '_3d_text_track_status'):
            self._3d_text_track_status.config(text=f"Tracking… {pct}%", fg=C["accent"])

    def _on_3d_text_autotrack_done(self, item, track):
        item['3d_text_track'] = track
        item['3d_text_full_clip'] = False
        item['3d_text_start'] = track['anchor_t']
        item['3d_text_end'] = track['tracked_until_t']
        dur = track['tracked_until_t'] - track['anchor_t']
        if hasattr(self, '_3d_text_track_status'):
            self._3d_text_track_status.config(
                text=f"Tracking locked ✓ ({dur:.1f}s — fades out once it moves out of view)", fg=C["accent3"])
        if hasattr(self, '_3d_text_track_btn'):
            self._3d_text_track_btn.config(state=tk.NORMAL)
        if self.selected_idx is not None and self.media_queue[self.selected_idx] is item:
            self._3d_text_full_clip.set(False)
            self._3d_text_start.set(track['anchor_t'])
            self._3d_text_end.set(track['tracked_until_t'])
        self.update_global_preview()

    def _on_3d_text_autotrack_error(self, item, msg):
        if hasattr(self, '_3d_text_track_status'):
            self._3d_text_track_status.config(text=msg, fg="#ff6b6b")
        if hasattr(self, '_3d_text_track_btn'):
            self._3d_text_track_btn.config(state=tk.NORMAL)

    def _clear_3d_text_autotrack(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        if '3d_text_track' in item:
            del item['3d_text_track']
        if hasattr(self, '_3d_text_track_status'):
            self._3d_text_track_status.config(text="Track cleared — text is fixed in place again", fg=C["text_dim"])
        self.update_global_preview()
