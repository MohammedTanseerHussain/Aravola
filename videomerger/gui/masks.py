"""Person mask extraction, refinement and keyframe handling.

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


class MasksMixin:
    """Person mask extraction, refinement and keyframe handling."""

    def _get_selected_person_mask(self, frame, item, t=None):
        """Get a mask for the selected person across ALL frames.
        Strategy: position-first tracking with appearance tie-breaking.
        Position is the strongest signal — the person can't teleport."""
        selected_id = int(item.get('effect_selected_person', -1))
        if selected_id < 0 and selected_id != -2:
            mask = self._get_mediapipe_mask(frame)
            if mask is not None:
                return mask
            return self._generate_mask_from_bbox(frame, (
                frame.shape[1] // 4, frame.shape[0] // 4,
                frame.shape[1] // 2, frame.shape[0] // 2))

        h, w = frame.shape[:2]
        empty_mask = np.zeros((h, w), dtype=np.float32)

        def _ready_mask(raw_mask, center, bbox):
            m = raw_mask
            if m.shape[:2] != (h, w):
                m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
            return self._trim_mask_overlap(m, center, bbox)

        predicted_center, predicted_bbox = self._predict_person_position(item, cur_w=w, cur_h=h)
        template = item.get('effect_person_template', None)
        has_previous_tracking = len(item.get('effect_tracking_keyframes', {})) > 0

        # ── EXACT KEYFRAME: this frame has a known-correct position ─────
        # already stored -- either the original selection click, or a
        # manual correction (Correct Here). Use it directly rather than
        # re-deriving it via search.
        t_now = t if t is not None else self.playhead_t.get()
        frame_idx_now = int(round(t_now * 30))
        exact_kf = item.get('effect_tracking_keyframes', {}).get(str(frame_idx_now))
        if exact_kf is not None:
            ex_center, ex_bbox = exact_kf.get('center'), exact_kf.get('bbox')
            ex_ref_w, ex_ref_h = exact_kf.get('ref_w'), exact_kf.get('ref_h')
            if ex_ref_w and ex_ref_h and (ex_ref_w != w or ex_ref_h != h):
                sx, sy = w / ex_ref_w, h / ex_ref_h
                ex_center = (ex_center[0] * sy, ex_center[1] * sx)
                ex_bbox = (ex_bbox[0] * sx, ex_bbox[1] * sy, ex_bbox[2] * sx, ex_bbox[3] * sy)
            item['effect_track_miss_streak'] = 0
            item['effect_last_match_frame_idx'] = frame_idx_now
            return self._make_person_bbox_mask(frame, ex_bbox)

        # ── STAGE 1: LOCAL correlation tracking (primary) ────────────────
        # See the note in _get_motion_track_position -- searching only a
        # small window around the predicted position means a similarly-
        # dressed neighbour can't be picked, and unlike YOLO-based
        # reacquisition below, it also works in frames where YOLO itself
        # doesn't detect anything nearby.
        template_patch = item.get('effect_track_template_patch')
        if template_patch is not None and predicted_center is not None:
            # Rescale the patch (and its inner offset) if it was captured
            # at a different resolution than this frame (e.g. preview vs.
            # export) -- see the matching note in _get_motion_track_position.
            inner_offset = item.get('effect_track_template_inner_offset')
            patch_ref_w, patch_ref_h = item.get('effect_track_template_ref_wh', (None, None))
            match_patch = template_patch
            match_offset = inner_offset
            if patch_ref_w and patch_ref_h and (patch_ref_w != w or patch_ref_h != h):
                psx, psy = w / patch_ref_w, h / patch_ref_h
                new_tw = max(3, int(template_patch.shape[1] * psx))
                new_th = max(3, int(template_patch.shape[0] * psy))
                try:
                    match_patch = cv2.resize(template_patch, (new_tw, new_th), interpolation=cv2.INTER_LINEAR)
                    if inner_offset:
                        match_offset = (int(inner_offset[0] * psx), int(inner_offset[1] * psy),
                                         int(inner_offset[2] * psx), int(inner_offset[3] * psy))
                except Exception:
                    match_patch = template_patch

            obj_w, obj_h = (predicted_bbox[2], predicted_bbox[3]) if predicted_bbox else (
                (match_offset[2], match_offset[3]) if match_offset else (match_patch.shape[1], match_patch.shape[0]))
            miss_streak = int(item.get('effect_track_miss_streak', 0))
            widen = 1.0 + min(miss_streak, 6) * 0.35
            search_radius = int(max(min(int(max(obj_w, obj_h) * 1.1), 80), 9) * widen)
            pcy, pcx = predicted_center
            local_hit = self._template_track_local(frame, match_patch, (pcx, pcy), search_radius)
            if local_hit is not None and local_hit['score'] >= 0.42:
                px, py, pw, ph = local_hit['bbox']
                if match_offset:
                    ox, oy, obw, obh = match_offset
                    bx, by, bw, bh = px + ox, py + oy, obw, obh
                else:
                    bx, by, bw, bh = px, py, pw, ph
                cy_hit, cx_hit = by + bh / 2.0, bx + bw / 2.0
                item['effect_track_miss_streak'] = 0
                self._update_tracking_keyframe(item, frame, (cy_hit, cx_hit), (bx, by, bw, bh), match_score=local_hit['score'], t=t)
                return self._make_person_bbox_mask(frame, (bx, by, bw, bh))
            else:
                item['effect_track_miss_streak'] = min(miss_streak + 1, 6)
        # ── STAGE 2: detector + appearance reacquisition (fallback) ──────

        yolo_persons = self._yolo_track(frame)
        if not yolo_persons:
            stored = item.get('effect_person_mask_template')
            if stored is not None and stored.max() > 0:
                if stored.shape[:2] != (h, w):
                    stored = cv2.resize(stored, (w, h), interpolation=cv2.INTER_LINEAR)
                return stored
            return empty_mask

        def _reidentify_and_return(matched_person, match_score=None):
            # VETO: re-check this candidate against the context-rich local
            # patch before accepting it. A colour histogram alone can be
            # fooled by a similarly-dressed neighbour; the specific
            # surrounding grass/lines/shadows at the wrong person's
            # position generally won't correlate well even when their
            # jersey colour does.
            mcy, mcx = matched_person['center']
            verify_score = self._verify_local_context(item, frame, (mcx, mcy))
            if verify_score is not None and verify_score < 0.25:
                print(f"[MASK-TRACK] REJECTED candidate: context_score={verify_score:.3f} < 0.25 -- likely wrong person, keeping last known mask")
                stored = item.get('effect_person_mask_template')
                if stored is not None and stored.max() > 0:
                    if stored.shape[:2] != (h, w):
                        stored = cv2.resize(stored, (w, h), interpolation=cv2.INTER_LINEAR)
                    return stored
                return empty_mask
            self._update_tracking_keyframe(item, frame, matched_person['center'], matched_person['bbox'], match_score=match_score, t=t)
            item['effect_track_miss_streak'] = 0
            if matched_person.get('raw_mask') is not None:
                return _ready_mask(matched_person['raw_mask'], matched_person['center'], matched_person['bbox'])
            return self._make_person_bbox_mask(frame, matched_person['bbox'])

        # Compute distance from each candidate to predicted position
        scored = []
        for p in yolo_persons:
            if predicted_center is not None:
                pcx, pcy = predicted_center[1], predicted_center[0]
                cx, cy = p['center'][1], p['center'][0]
                pos_dist = ((pcx - cx) ** 2 + (pcy - cy) ** 2) ** 0.5
            else:
                pos_dist = 0
            scored.append((p, pos_dist))

        scored.sort(key=lambda x: x[1])

        # Tight, SIZE-AWARE tolerance -- see the note in
        # _get_motion_track_position for why a fixed frame-fraction gate
        # (the old 30-40%) is far too loose for crowded, small-subject
        # scenes and lets the wrong, similarly-dressed person win.
        max_dim = max(h, w)
        ref_w, ref_h = (predicted_bbox[2], predicted_bbox[3]) if predicted_bbox else (None, None)
        ref_diag = (ref_w ** 2 + ref_h ** 2) ** 0.5 if (ref_w and ref_h) else max_dim * 0.04
        max_close_dist = min(max(ref_diag * 4.0, max_dim * 0.05), max_dim * 0.16)
        close_candidates = [(p, d) for p, d in scored if d < max_close_dist]

        if template is not None and len(close_candidates) >= 1:
            face_buffer = item.get('effect_face_buffer', [])
            best_match, best_score = self._match_person_to_template(
                frame, [p for p, _ in close_candidates], template,
                last_center=predicted_center, face_buffer=face_buffer,
                max_spatial_dist=max_close_dist)
            if best_match >= 0 and best_score > 0.15:
                return _reidentify_and_return(close_candidates[best_match][0], best_score)

        if len(close_candidates) == 1:
            return _reidentify_and_return(close_candidates[0][0])

        # Wider search with appearance -- still gated, just a looser radius
        top_candidates = scored[:min(5, len(scored))]
        if template is not None and top_candidates:
            face_buffer = item.get('effect_face_buffer', [])
            best_match, best_score = self._match_person_to_template(
                frame, [p for p, _ in top_candidates], template,
                last_center=predicted_center, face_buffer=face_buffer,
                max_spatial_dist=max_close_dist * 2.0)
            if best_match >= 0 and best_score > 0.25:
                return _reidentify_and_return(top_candidates[best_match][0], best_score)

        # Low confidence — keep using stored template mask instead of switching
        stored = item.get('effect_person_mask_template')
        if stored is not None and stored.max() > 0:
            if stored.shape[:2] != (h, w):
                stored = cv2.resize(stored, (w, h), interpolation=cv2.INTER_LINEAR)
            return stored

        # Absolute last resort: closest person
        matched = scored[0][0]
        return _reidentify_and_return(matched)

    def _color_segment_person(self, frame, click_x, click_y, radius=None):
        """Build a person mask by sampling colors around the click point and
        using HSV back-projection + GrabCut. This avoids MediaPipe noise entirely."""
        h, w = frame.shape[:2]
        if radius is None:
            radius = max(30, min(h, w) // 10)

        # Sample colors from a small patch around the click point
        x0 = max(0, click_x - radius)
        y0 = max(0, click_y - radius)
        x1 = min(w, click_x + radius)
        y1 = min(h, click_y + radius)
        sample_patch = frame[y0:y1, x0:x1]
        if sample_patch.size == 0:
            return np.zeros((h, w), dtype=np.float32)

        # Build 2D HSV histogram (H+S) from the sample patch
        hsv_sample = cv2.cvtColor(sample_patch, cv2.COLOR_RGB2HSV)
        hist = cv2.calcHist([hsv_sample], [0, 1], None, [30, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 255, cv2.NORM_MINMAX)

        # Back-project onto full frame
        hsv_full = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
        back_proj = cv2.calcBackProject([hsv_full], [0, 1], hist, [0, 180, 0, 256], 1.0)

        # Threshold to get binary mask
        _, mask = cv2.threshold(back_proj, 30, 255, cv2.THRESH_BINARY)

        # Morphological cleanup
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
        mask = cv2.medianBlur(mask, 7)

        # Find connected components, keep the one nearest to click
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        best_label = -1
        best_dist = float('inf')
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 500:
                continue
            cx, cy = centroids[i]
            dist = ((click_x - cx) ** 2 + (click_y - cy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_label = i
        if best_label < 0:
            return np.zeros((h, w), dtype=np.float32)

        clean = np.zeros((h, w), dtype=np.uint8)
        clean[labels == best_label] = 255

        # GrabCut refinement using the color mask as guide
        comp_x = stats[best_label, cv2.CC_STAT_LEFT]
        comp_y = stats[best_label, cv2.CC_STAT_TOP]
        comp_w = stats[best_label, cv2.CC_STAT_WIDTH]
        comp_h = stats[best_label, cv2.CC_STAT_HEIGHT]
        pad_x = max(15, int(comp_w * 0.15))
        pad_y = max(15, int(comp_h * 0.15))
        rx0 = max(0, comp_x - pad_x)
        ry0 = max(0, comp_y - pad_y)
        rx1 = min(w, comp_x + comp_w + pad_x)
        ry1 = min(h, comp_y + comp_h + pad_y)
        if rx1 - rx0 >= 30 and ry1 - ry0 >= 30:
            try:
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                gc_mask = np.zeros((h, w), np.uint8)
                gc_mask[:] = cv2.GC_BGD
                gc_mask[rx0:rx1, ry0:ry1] = cv2.GC_PR_FGD
                gc_mask[clean > 200] = cv2.GC_FGD
                bgd_model = np.zeros((1, 64), np.float64)
                fgd_model = np.zeros((1, 64), np.float64)
                rect = (rx0, ry0, rx1 - rx0, ry1 - ry0)
                cv2.grabCut(frame_bgr, gc_mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_MASK)
                clean = np.where((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
            except Exception:
                pass

        result = clean.astype(np.float32) / 255.0
        result = cv2.GaussianBlur(result, (5, 5), 0)
        return result

    def _clean_person_mask(self, mask, reference_center=None, bbox=None, frame=None):
        """Remove noise and produce a tight person mask.
        Uses morphological cleanup, connected-component filtering, and optionally
        GrabCut (when frame+bbox provided) to separate person from background using color."""
        h, w = mask.shape[:2]
        mask_uint8 = (mask * 255).astype(np.uint8)

        # --- Stage 1: Morphological cleanup ---
        erode_k = np.ones((7, 7), np.uint8)
        mask_uint8 = cv2.erode(mask_uint8, erode_k, iterations=3)
        open_k = np.ones((5, 5), np.uint8)
        mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_OPEN, open_k, iterations=2)
        mask_uint8 = cv2.medianBlur(mask_uint8, 7)

        # --- Stage 2: Connected-component spatial filter ---
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_uint8, connectivity=8)
        if num_labels <= 1:
            return np.zeros((h, w), dtype=np.float32)

        best_label = -1
        best_score = -1
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 150:
                continue
            cx, cy = centroids[i]
            if bbox is not None:
                bx, by, bw, bh = bbox
                pad_x = int(bw * 0.3)
                pad_y = int(bh * 0.3)
                bx0, by0 = max(0, bx - pad_x), max(0, by - pad_y)
                bx1, by1 = min(w, bx + bw + pad_x), min(h, by + bh + pad_y)
                if cx < bx0 or cx > bx1 or cy < by0 or cy > by1:
                    continue
            if reference_center is not None:
                rcx, rcy = reference_center[1], reference_center[0]
                dist = ((cx - rcx) ** 2 + (cy - rcy) ** 2) ** 0.5
                score = area - dist * 100
            else:
                score = area
            if score > best_score:
                best_score = score
                best_label = i

        if best_label < 0:
            return np.zeros((h, w), dtype=np.float32)

        clean = np.zeros_like(mask_uint8)
        clean[labels == best_label] = mask_uint8[labels == best_label]

        # --- Stage 3: GrabCut refinement (separate person from background by color) ---
        if frame is not None and bbox is not None:
            refined = self._refine_mask_grabcut(frame, clean, bbox)
            if refined is not None:
                clean = refined

        # --- Stage 4: Final polish ---
        close_k = np.ones((9, 9), np.uint8)
        clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, close_k, iterations=2)
        result = clean.astype(np.float32) / 255.0
        result = cv2.GaussianBlur(result, (5, 5), 0)
        return result

    def _refine_mask_grabcut(self, frame, mask_uint8, bbox):
        """Use GrabCut in RECT-ONLY mode to separate person from background by color.
        First erodes aggressively to find the person's core, then uses that tight
        bbox for GrabCut so background objects outside the core are excluded."""
        h, w = frame.shape[:2]

        # Step 1: Erode aggressively to find the person's inner core
        core = cv2.erode(mask_uint8, np.ones((11, 11), np.uint8), iterations=5)
        core = cv2.medianBlur(core, 7)
        core_binary = (core > 127).astype(np.uint8)

        # Step 2: Find the core's bbox (tight around the person only)
        ys, xs = np.where(core_binary > 0)
        if len(xs) < 100 or len(ys) < 100:
            return None
        cx0, cy0 = int(xs.min()), int(ys.min())
        cx1, cy1 = int(xs.max()), int(ys.max())
        core_w = cx1 - cx0
        core_h = cy1 - cy0
        if core_w < 15 or core_h < 15:
            return None

        # Step 3: Expand core bbox with padding for GrabCut context
        pad_x = max(15, int(core_w * 0.2))
        pad_y = max(15, int(core_h * 0.2))
        rx0 = max(0, cx0 - pad_x)
        ry0 = max(0, cy0 - pad_y)
        rx1 = min(w, cx1 + pad_x)
        ry1 = min(h, cy1 + pad_y)
        if rx1 - rx0 < 30 or ry1 - ry0 < 30:
            return None

        try:
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            bgd_model = np.zeros((1, 64), np.float64)
            fgd_model = np.zeros((1, 64), np.float64)
            rect = (rx0, ry0, rx1 - rx0, ry1 - ry0)
            gc_mask = np.zeros((h, w), np.uint8)
            # Pure rectangle mode — GrabCut figures out person by color
            cv2.grabCut(frame_bgr, gc_mask, rect, bgd_model, fgd_model, 8, cv2.GC_INIT_WITH_RECT)
            result = np.where((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)

            # Step 4: Keep only the largest component overlapping the core center
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(result, connectivity=8)
            core_cx = (cx0 + cx1) // 2
            core_cy = (cy0 + cy1) // 2
            best_label = -1
            best_area = 0
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                if area < 300:
                    continue
                ccx = stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] // 2
                ccy = stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] // 2
                dist = ((ccx - core_cx) ** 2 + (ccy - core_cy) ** 2) ** 0.5
                max_dist = max(core_w, core_h) * 0.7
                if dist < max_dist and area > best_area:
                    best_area = area
                    best_label = i
            if best_label > 0:
                refined = np.zeros_like(result)
                refined[labels == best_label] = 255
                return refined
        except Exception as e:
            print(f"GrabCut refinement failed: {e}")
        return None

    def _predict_person_position(self, item, cur_w=None, cur_h=None):
        """Chain-reaction position: returns the MOST RECENTLY CONFIRMED
        position, rescaled to the current frame's resolution if needed.
        Each frame's real, matched position becomes the search anchor for
        the next frame -- deliberately NOT velocity-extrapolated. An
        extrapolation guess is a second thing that can be wrong on top of
        the matcher itself, and with the tight local search window used
        elsewhere, the last real position is already a better anchor than
        a guess about where the object "should" be next.
        Returns (predicted_center, predicted_bbox) or (None, None).

        `cur_w`/`cur_h`: dimensions of the frame this will be used
        against. Preview renders at a fixed small canvas (e.g. 960x540)
        while export renders at the actual output resolution (e.g.
        1920x1080) -- a position captured during one and used unscaled
        against the other would be off by exactly that ratio. The latest
        keyframe remembers the (ref_w, ref_h) of the frame it was
        captured at, so it gets rescaled into `cur_w`/`cur_h` space here.
        If `cur_w`/`cur_h` aren't given, the position is returned as
        originally stored (unscaled)."""
        keyframes = item.get('effect_tracking_keyframes', {})
        if not keyframes:
            return None, None
        sorted_keys = sorted(keyframes.keys(), key=lambda k: int(k))
        if len(sorted_keys) == 0:
            return None, None

        kf = keyframes[sorted_keys[-1]]
        center, bbox = kf.get('center'), kf.get('bbox')
        ref_w, ref_h = kf.get('ref_w'), kf.get('ref_h')
        if not (cur_w and cur_h and ref_w and ref_h) or (ref_w == cur_w and ref_h == cur_h):
            return center, bbox
        sx, sy = cur_w / ref_w, cur_h / ref_h
        rc = (center[0] * sy, center[1] * sx) if center else None
        rb = (bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy) if bbox else None
        return rc, rb

    def _update_tracking_keyframe(self, item, frame, center, bbox, match_score=None, t=None):
        """Store or update the latest tracking keyframe and face buffer.
        Only updates on high-confidence matches to prevent drift.
        `t`: the actual time (seconds) of the frame being processed.
        IMPORTANT: this must be the frame's own time, not read from the
        live GUI playhead -- during export, frames are rendered one after
        another with no relation to wherever the playhead slider happens
        to be sitting, so relying on it collapses every exported frame's
        keyframe onto the same timestamp, silently breaking velocity
        prediction and the drift-history entirely. Falls back to the
        live playhead only when `t` isn't supplied (e.g. interactive
        mask-painting UI callers that only ever run against the frame
        currently on screen).
        `match_score`, if given, also gates whether the local-tracking
        template patch gets refreshed from this position (see
        _maybe_refresh_track_template) -- a low-confidence fallback match
        shouldn't be allowed to slowly drag that patch toward the wrong
        object.
        Face features are appended to a rolling buffer (not blended),
        so the system remembers the person at different distances/angles."""
        if t is None:
            t = self.playhead_t.get()
        frame_idx = int(round(t * 30))
        keyframes = item.get('effect_tracking_keyframes', {})

        # Sanity-check the new position against where we predicted this
        # object to be, using a SIZE-AWARE radius (see the note in
        # _get_motion_track_position). A wildly-off position isn't just a
        # bad appearance-template update — if it gets written into the
        # keyframe history unconditionally (the old behaviour), it also
        # poisons the velocity prediction used for every frame after this
        # one, letting a single bad match cascade into a runaway drift
        # instead of self-correcting.
        num_keyframes = len(keyframes)
        h, w = frame.shape[:2]
        predicted_center, _ = self._predict_person_position(item, cur_w=w, cur_h=h)
        max_dim = max(h, w)
        bw, bh = bbox[2], bbox[3]
        ref_diag = (bw ** 2 + bh ** 2) ** 0.5 if (bw and bh) else max_dim * 0.04
        max_drift = min(max(ref_diag * 4.0, max_dim * 0.05), max_dim * 0.16)

        if predicted_center is not None and num_keyframes > 3:
            pcx, pcy = predicted_center[1], predicted_center[0]
            cx, cy = center[1], center[0]
            dist = ((pcx - cx) ** 2 + (pcy - cy) ** 2) ** 0.5
            if dist > max_drift:
                return  # don't let a far-off match corrupt the tracking history

        key = str(frame_idx)
        keyframes[key] = {
            'center': center,
            'bbox': bbox,
            'time': t,
            'ref_w': w,
            'ref_h': h,
        }
        # Keep only last 60 keyframes
        if len(keyframes) > 60:
            sorted_keys = sorted(keyframes.keys(), key=lambda k: int(k))
            for old_key in sorted_keys[:-60]:
                del keyframes[old_key]
        item['effect_tracking_keyframes'] = keyframes
        self._maybe_refresh_track_template(item, frame, bbox, score=match_score)

        # Extract appearance features
        new_app = self._get_person_appearance(frame, bbox)
        if new_app is None:
            return

        # Append new face features to rolling buffer (NOT blended)
        # This preserves distinctive face features at different distances/angles
        face_buffer = item.get('effect_face_buffer', [])
        if new_app.get('face_embedding') is not None or new_app.get('face_hist') is not None:
            face_buffer.append(new_app)
        # Keep max 12 face samples — enough for multi-scale matching, not too old
        if len(face_buffer) > 12:
            face_buffer = face_buffer[-12:]
        item['effect_face_buffer'] = face_buffer

        # Also keep main template updated with body histogram (body changes slowly, blend is fine)
        old_template = item.get('effect_person_template')
        if old_template is not None and new_app.get('body_hist') is not None and old_template.get('body_hist') is not None:
            new_app['body_hist'] = old_template['body_hist'] * 0.8 + new_app['body_hist'] * 0.2
        item['effect_person_template'] = new_app

    def _trim_mask_overlap(self, mask, center, bbox):
        """Light cleanup to remove edge bleed from nearby people.
        Trims overlapping edges and keeps only the main person blob."""
        h, w = mask.shape[:2]
        mask_uint8 = (mask * 255).astype(np.uint8) if mask.dtype != np.uint8 else mask

        # Light erosion to trim thin overlapping edges
        erode_k = np.ones((3, 3), np.uint8)
        trimmed = cv2.erode(mask_uint8, erode_k, iterations=1)

        # Keep only the largest connected component near the person's center
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(trimmed, connectivity=8)
        if num_labels <= 1:
            return mask  # nothing to trim

        cx, cy = center[1], center[0]
        best_label = -1
        best_score = -1
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 200:
                continue
            ccx, ccy = centroids[i]
            dist = ((cx - ccx) ** 2 + (cy - ccy) ** 2) ** 0.5
            # Score: large area + close to center = best
            score = area - dist * 30
            if score > best_score:
                best_score = score
                best_label = i

        if best_label < 0:
            return mask

        clean = np.zeros_like(mask_uint8)
        clean[labels == best_label] = mask_uint8[labels == best_label]
        result = clean.astype(np.float32) / 255.0
        result = cv2.GaussianBlur(result, (3, 3), 0)
        return result

    def _make_person_bbox_mask(self, frame, bbox, full_mask=None):
        """Create a person mask by isolating a bbox region from a full mask,
        or generating a GrabCut mask when no full mask is available."""
        h, w = frame.shape[:2]
        x, y, bw, bh = bbox
        pad_x = int(bw * 0.15)
        pad_y = int(bh * 0.10)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_y)
        x1 = min(w, x + bw + pad_x)
        y1 = min(h, y + bh + pad_y)
        if full_mask is not None:
            person_mask = np.zeros((h, w), dtype=np.float32)
            person_mask[y0:y1, x0:x1] = full_mask[y0:y1, x0:x1]
            # Clean up: keep only the largest connected component in the bbox
            binary = (person_mask > 0.3).astype(np.uint8)
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
            if num_labels > 1:
                # Find largest component that overlaps the bbox center
                cx, cy = x0 + (x1 - x0) // 2, y0 + (y1 - y0) // 2
                best_label = -1
                best_area = 0
                for i in range(1, num_labels):
                    area = stats[i, cv2.CC_STAT_AREA]
                    lx = stats[i, cv2.CC_STAT_LEFT]
                    ly = stats[i, cv2.CC_STAT_TOP]
                    lw = stats[i, cv2.CC_STAT_WIDTH]
                    lh = stats[i, cv2.CC_STAT_HEIGHT]
                    # Check if component center is near the bbox center
                    ccx = lx + lw // 2
                    ccy = ly + lh // 2
                    dist = ((ccx - cx) ** 2 + (ccy - cy) ** 2) ** 0.5
                    max_dist = max(bw, bh) * 0.8
                    if dist < max_dist and area > best_area:
                        best_area = area
                        best_label = i
                if best_label > 0:
                    person_mask = np.zeros((h, w), dtype=np.float32)
                    person_mask[labels == best_label] = full_mask[labels == best_label]
            # Clean and smooth edges
            ref_center = (y0 + (y1 - y0) // 2, x0 + (x1 - x0) // 2)
            person_mask = self._clean_person_mask(person_mask, ref_center, (x, y, bw, bh), frame)
            if person_mask.max() > 0.01:
                return person_mask
        return self._generate_mask_from_bbox(frame, bbox)

    def _track_person_across_frames(self, item, frame_idx, persons, selected_id):
        """Store initial tracking keyframe and template when person is first selected."""
        if selected_id < 0 or selected_id >= len(persons):
            selected_id = 0
        chosen = persons[selected_id]
        frame = self._get_preview_frame(item)
        fw, fh = (frame.shape[1], frame.shape[0]) if frame is not None else (None, None)
        # Start a FRESH tracking history for this newly-selected object.
        # Carrying over keyframes left behind by a PREVIOUS selection
        # corrupts the velocity prediction used every frame afterwards and
        # can pull the tracker toward the old target instead of the one
        # just picked.
        item['effect_tracking_keyframes'] = {
            str(frame_idx): {
                'center': chosen['center'],
                'bbox': chosen['bbox'],
                'person_id': selected_id,
                'time': self.playhead_t.get(),
                'ref_w': fw,
                'ref_h': fh,
            }
        }
        item['effect_track_miss_streak'] = 0
        item['effect_last_match_frame_idx'] = frame_idx
        # Store appearance template for cross-frame tracking
        if frame is not None:
            new_app = self._get_person_appearance(frame, chosen['bbox'])
            if new_app is not None:
                item['effect_person_template'] = new_app
            item['effect_track_template_patch'], item['effect_track_template_inner_offset'] = self._extract_track_template_patch(frame, chosen['bbox'])
            item['effect_track_template_ref_wh'] = (fw, fh)

    def _get_tracked_center_for_frame(self, item, frame_idx):
        keyframes = item.get('effect_tracking_keyframes', {})
        key = str(frame_idx)
        if key in keyframes:
            return keyframes[key]['center'], keyframes[key]['bbox']
        sorted_keys = sorted(keyframes.keys(), key=lambda k: int(k))
        if not sorted_keys:
            return None, None
        before = [k for k in sorted_keys if int(k) <= frame_idx]
        after = [k for k in sorted_keys if int(k) > frame_idx]
        if before and after:
            k0, k1 = before[-1], after[0]
            t0, t1 = int(k0), int(k1)
            alpha = (frame_idx - t0) / max(1, t1 - t0)
            c0 = keyframes[k0]['center']
            c1 = keyframes[k1]['center']
            cy = int(c0[0] + alpha * (c1[0] - c0[0]))
            cx = int(c0[1] + alpha * (c1[1] - c0[1]))
            b0 = keyframes[k0]['bbox']
            bw = int(b0[2] + alpha * (keyframes[k1]['bbox'][2] - b0[2]))
            bh = int(b0[3] + alpha * (keyframes[k1]['bbox'][3] - b0[3]))
            bx = int(cx - bw // 2)
            by = int(cy - bh // 2)
            return (cy, cx), (bx, by, bw, bh)
        elif before:
            k0 = before[-1]
            return keyframes[k0]['center'], keyframes[k0]['bbox']
        else:
            k0 = after[0]
            return keyframes[k0]['center'], keyframes[k0]['bbox']

    def _detect_subject_center(self, frame):
        h, w = frame.shape[:2]
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            face_cascade = cv2.CascadeClassifier(
                _HAAR_CASCADE_PATH
            )
            faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
            if len(faces) > 0:
                largest = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = largest
                return (fy + fh // 2, fx + fw // 2)
        except Exception:
            pass
        gray = frame.mean(axis=2).astype(np.float32)
        Y, X = np.mgrid[:h, :w]
        center_bias = np.exp(-0.5 * (((X - w / 2) / (w * 0.3)) ** 2 + ((Y - h / 2) / (h * 0.3)) ** 2))
        weighted = gray * center_bias
        total = weighted.sum()
        if total > 0:
            cy = int((Y * weighted).sum() / total)
            cx = int((X * weighted).sum() / total)
            return (cy, cx)
        return (h // 2, w // 2)
