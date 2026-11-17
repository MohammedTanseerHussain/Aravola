"""Motion-track arrow and label rendering.

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


class EffectsMotionMixin:
    """Motion-track arrow and label rendering."""

    def _get_motion_track_position(self, frame, item, t):
        """Get the tracked object's center and bbox. Uses YOLO detection,
        position prediction, appearance matching, and keyframe interpolation.
        Returns (cx, cy, bbox, matched)."""
        h, w = frame.shape[:2]
        selected_id = int(item.get('effect_selected_person', -1))
        has_template = item.get('effect_person_template') is not None
        has_keyframes = len(item.get('effect_tracking_keyframes', {})) > 0
        selected_class = item.get('effect_selected_class', None)
        person_selected = selected_id >= 0 or selected_id == -2

        # Run YOLO detection
        yolo_objects = self._yolo_track(frame)

        # ── No object selected AND no template: pick closest to frame center ──
        if not person_selected and not has_template:
            if yolo_objects:
                cy_mid, cx_mid = h // 2, w // 2
                best = min(yolo_objects, key=lambda p: (
                    (p['center'][0] - cy_mid)**2 + (p['center'][1] - cx_mid)**2))
                return (best['center'][1], best['center'][0], best['bbox'], True)
            return (None, None, None, False)

        # ── Object selected (or template exists): use full tracking pipeline ──
        predicted_center, predicted_bbox = self._predict_person_position(item, cur_w=w, cur_h=h)
        template = item.get('effect_person_template', None)
        face_buffer = item.get('effect_face_buffer', [])
        max_dim = max(h, w)

        # ── EXACT KEYFRAME: this frame has a known-correct position ─────
        # already stored -- either the original selection click, or a
        # manual correction (Correct Here). Use it directly rather than
        # re-deriving it via search, so the selection/correction point
        # itself is always pixel-exact, never second-guessed.
        frame_idx_now = int(round(t * 30))
        exact_kf = item.get('effect_tracking_keyframes', {}).get(str(frame_idx_now))
        if exact_kf is not None:
            ex_center, ex_bbox = exact_kf.get('center'), exact_kf.get('bbox')
            ex_ref_w, ex_ref_h = exact_kf.get('ref_w'), exact_kf.get('ref_h')
            if ex_ref_w and ex_ref_h and (ex_ref_w != w or ex_ref_h != h):
                sx, sy = w / ex_ref_w, h / ex_ref_h
                ex_center = (ex_center[0] * sy, ex_center[1] * sx)
                ex_bbox = (ex_bbox[0] * sx, ex_bbox[1] * sy, ex_bbox[2] * sx, ex_bbox[3] * sy)
            ex_cy, ex_cx = ex_center
            item['effect_track_miss_streak'] = 0
            item['effect_last_match_frame_idx'] = frame_idx_now
            return (ex_cx, ex_cy, ex_bbox, True)

        # ── STAGE 1: LOCAL correlation tracking (primary) ───────────────
        # Search only a small window around the predicted position for the
        # exact pixel pattern grabbed at selection time (or last refreshed).
        # A lookalike neighbour standing even a short distance away never
        # enters this window, so it structurally cannot be picked here --
        # unlike Stage 2 below, which searches the whole frame and can be
        # fooled by near-identical appearance (e.g. teammates in the same
        # kit). Stage 2 only runs when Stage 1 doesn't find a confident
        # match -- e.g. right after selection (no patch refresh yet isn't
        # the case, selection already seeds one), after a big timeline
        # jump/scrub, or once the tracked object reappears from an absence.
        template_patch = item.get('effect_track_template_patch')
        if template_patch is not None and predicted_center is not None:
            # The patch may have been captured at a DIFFERENT resolution
            # than this frame -- preview renders at a fixed small canvas
            # while export renders at the actual output resolution, so a
            # patch grabbed during preview is the wrong physical size for
            # matching against an export-resolution frame. Rescale it (and
            # the inner-offset that locates the real object within it) to
            # match this frame before searching.
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
            # Tight radius: real frame-to-frame motion is small (a few px
            # at typical framerates). The old 2.5x multiplier produced a
            # ~140px-wide window for a 15px player -- easily wide enough
            # to reach a neighbour standing nearby, which is what let the
            # arrow hop between people. A big jump (fast pan, scrub) will
            # simply miss here and fall through to Stage 2 instead, which
            # is the right behaviour -- Stage 1 should only claim "same
            # person" when the evidence is tight, not stretch to cover
            # cases it can't reliably distinguish.
            #
            # That said, a SHORT run of consecutive misses (motion blur on
            # a fast movement, a brief partial occlusion) shouldn't force
            # a drop to the weaker Stage 2 on every single one of those
            # frames -- each additional consecutive miss widens the search
            # a bit further (capped), so a brief rough patch can still be
            # bridged by the strong, context-aware Stage 1 match instead of
            # repeatedly falling back or eventually hiding the arrow. It
            # snaps back to the tight radius the moment a match succeeds.
            miss_streak = int(item.get('effect_track_miss_streak', 0))
            widen = 1.0 + min(miss_streak, 6) * 0.35
            search_radius = int(max(min(int(max(obj_w, obj_h) * 1.1), 80), 9) * widen)
            pcy, pcx = predicted_center
            local_hit = self._template_track_local(frame, match_patch, (pcx, pcy), search_radius)
            LOCAL_MATCH_THRESHOLD = 0.42
            if local_hit is not None and local_hit['score'] >= LOCAL_MATCH_THRESHOLD:
                px, py, pw, ph = local_hit['bbox']  # position of the (padded, context-including) patch
                if match_offset:
                    ox, oy, obw, obh = match_offset
                    bx, by, bw, bh = px + ox, py + oy, obw, obh  # the object's own tight bbox
                else:
                    bx, by, bw, bh = px, py, pw, ph
                cx, cy = bx + bw / 2.0, by + bh / 2.0
                print(f"[LOCAL-TRACK] score={local_hit['score']:.3f} pos=({cx:.0f},{cy:.0f}) window_r={search_radius} miss_streak={miss_streak}")
                item['effect_track_miss_streak'] = 0
                self._update_tracking_keyframe(item, frame, (cy, cx), (bx, by, bw, bh), match_score=local_hit['score'], t=t)
                return (cx, cy, (bx, by, bw, bh), True)
            elif local_hit is not None:
                print(f"[LOCAL-TRACK] below threshold: score={local_hit['score']:.3f} < {LOCAL_MATCH_THRESHOLD} -- falling back to detector")
            item['effect_track_miss_streak'] = min(int(item.get('effect_track_miss_streak', 0)) + 1, 6)
        # ── STAGE 2: detector + appearance reacquisition (fallback) ─────

        if yolo_objects:
            # Filter by same class if we know what we're tracking
            if selected_class:
                same_class = [p for p in yolo_objects if p.get('class_name') == selected_class]
                search_pool = same_class if same_class else yolo_objects
            else:
                search_pool = yolo_objects

            # Score candidates by distance to predicted position
            scored = []
            for p in search_pool:
                if predicted_center is not None:
                    pcx, pcy = predicted_center[1], predicted_center[0]
                    cx, cy = p['center'][1], p['center'][0]
                    pos_dist = ((pcx - cx) ** 2 + (pcy - cy) ** 2) ** 0.5
                else:
                    pos_dist = 0
                # Boost score for same YOLO track ID (strong identity signal)
                id_bonus = 0
                if person_selected and p.get('id') == selected_id:
                    id_bonus = max_dim * 0.15
                scored.append((p, max(0, pos_dist - id_bonus)))
            scored.sort(key=lambda x: x[1])

            # Tight, SIZE-AWARE tolerance: a real person can't jump more
            # than a few multiples of their own on-screen size between two
            # frames a fraction of a second apart. Gating on a fixed
            # fraction of the WHOLE frame (the old behaviour: 40-50%) is far
            # too loose in a wide shot crowded with small, similarly-
            # dressed subjects — it lets appearance-match noise on a tiny
            # crop pick a completely different person clear across the
            # pitch, which is exactly what was happening.
            ref_w, ref_h = (predicted_bbox[2], predicted_bbox[3]) if predicted_bbox else (None, None)
            if ref_w and ref_h:
                ref_diag = (ref_w ** 2 + ref_h ** 2) ** 0.5
            else:
                ref_diag = max_dim * 0.04
            max_close_dist = min(max(ref_diag * 4.0, max_dim * 0.05), max_dim * 0.16)
            close_candidates = [(p, d) for p, d in scored if d < max_close_dist]
            if not close_candidates:
                close_candidates = scored[:3]

            if has_template and close_candidates:
                cand_list = [p for p, _ in close_candidates]
                best_idx, app_score = self._match_person_to_template(
                    frame, cand_list, template,
                    last_center=predicted_center, face_buffer=face_buffer,
                    max_spatial_dist=max_close_dist)
                if best_idx >= 0:
                    matched = cand_list[best_idx]
                    cx, cy = matched['center'][1], matched['center'][0]
                    # VETO: a colour histogram alone can be fooled by a
                    # similarly-dressed neighbour. Re-check this exact
                    # candidate against the context-rich local patch before
                    # accepting it as the new chain anchor.
                    verify_score = self._verify_local_context(item, frame, (cx, cy))
                    if verify_score is not None and verify_score < 0.25:
                        print(f"[MOTION-TRACK] REJECTED class_match: app_score={app_score:.3f} but context_score={verify_score:.3f} < 0.25 -- likely wrong person")
                    else:
                        print(f"[MOTION-TRACK] class_match={matched.get('class_name','?')} app_score={app_score:.3f} context_score={verify_score} pos=({cx},{cy})")
                        item['effect_track_miss_streak'] = 0
                        self._update_tracking_keyframe(item, frame, matched['center'], matched['bbox'], match_score=app_score, t=t)
                        return (cx, cy, matched['bbox'], True)
                else:
                    print(f"[MOTION-TRACK] no_app_match class={selected_class} candidates={len(close_candidates)}")

            # Fallback: when a person is selected, prefer same-class detections
            # and use YOLO ID as tiebreaker to avoid jumping to wrong person
            if scored:
                if person_selected and selected_class:
                    same_class_scored = [(p, d) for p, d in scored if p.get('class_name') == selected_class]
                    if same_class_scored:
                        scored = same_class_scored
                # Among equal-distance candidates, prefer matching YOLO ID
                best_p = scored[0][0]
                for p, d in scored[:5]:
                    if person_selected and p.get('id') == selected_id:
                        best_p = p
                        break
                cx, cy = best_p['center'][1], best_p['center'][0]
                # This fallback has NO appearance confirmation at all -- it's
                # the weakest signal in the whole pipeline, so require the
                # local-context check to pass before accepting it.
                verify_score = self._verify_local_context(item, frame, (cx, cy))
                if verify_score is not None and verify_score < 0.25:
                    print(f"[MOTION-TRACK] REJECTED pos_fallback: context_score={verify_score:.3f} < 0.25 -- likely wrong person")
                else:
                    print(f"[MOTION-TRACK] pos_fallback class={best_p.get('class_name','?')} id={best_p.get('id','?')} context_score={verify_score} pos=({cx},{cy})")
                    item['effect_track_miss_streak'] = 0
                    self._update_tracking_keyframe(item, frame, best_p['center'], best_p['bbox'], match_score=0.0, t=t)
                    return (cx, cy, best_p['bbox'], True)

        # ── No YOLO detections: use prediction + keyframe interpolation ──
        if predicted_center is not None:
            bbox = predicted_bbox if predicted_bbox is not None else None
            if bbox is None and has_keyframes:
                frame_idx = int(t * 30)
                _, interp_bbox = self._get_tracked_center_for_frame(item, frame_idx)
                bbox = interp_bbox if interp_bbox else None
            return (predicted_center[1], predicted_center[0], bbox, False)

        # ── Last resort: use keyframe interpolation ──
        if has_keyframes:
            frame_idx = int(t * 30)
            interp_center, interp_bbox = self._get_tracked_center_for_frame(item, frame_idx)
            if interp_center is not None:
                return (interp_center[1], interp_center[0], interp_bbox, False)

        return (None, None, None, False)

    def apply_motion_track_effect(self, frame, item, t):
        """Draw a colored arrow + optional name label tracking a person.
        Uses the full tracking pipeline: YOLO detection, position prediction,
        appearance matching (face + clothing color + edge template), and
        keyframe interpolation for frame-to-frame continuity."""
        if not item.get('effect_motion_track_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame

        cx, cy, bbox, matched = self._get_motion_track_position(frame, item, t)

        if cx is None or cy is None:
            return frame

        # ── PRESENCE GATE ──────────────────────────────────────────────
        # `matched` is True only when the tracked object was genuinely
        # detected in THIS frame (appearance match or same-class YOLO
        # fallback). When it's False, cx/cy/bbox came only from velocity
        # prediction or keyframe interpolation -- a guess, not a sighting.
        # Keep drawing through a short grace window so a single missed
        # detection doesn't cause 1-frame flicker, but once the person/
        # object has genuinely left the shot for longer than that, hide
        # the arrow instead of letting it drift on a stale guess.
        frame_idx = int(round(t * 30))
        GRACE_FRAMES = 10  # ~0.33s at 30fps
        if matched:
            item['effect_track_miss_streak'] = 0
            item['effect_last_match_frame_idx'] = frame_idx
        else:
            last_match = item.get('effect_last_match_frame_idx', None)
            if last_match is None or abs(frame_idx - last_match) > GRACE_FRAMES:
                return frame
        # ─────────────────────────────────────────────────────────────────
        # Get settings
        mode = item.get('motion_track_mode', 'arrow_and_name')
        name = item.get('motion_track_name', '')
        color_name = item.get('motion_track_color', 'Yellow')
        text_color_name = item.get('motion_track_text_color', 'Yellow')
        arrow_size = float(item.get('motion_track_arrow_size', 1.0))
        arrow_len = float(item.get('motion_track_arrow_len', 1.0))
        text_size = float(item.get('motion_track_text_size', 1.0))
        offset_y = float(item.get('motion_track_offset_y', 0.0))

        arrow_bgr = self.MOTION_TRACK_COLORS.get(color_name, (0, 255, 255))
        text_bgr = self.MOTION_TRACK_COLORS.get(text_color_name, (0, 255, 255))

        # Convert BGR to RGB for numpy drawing
        arrow_rgb = (arrow_bgr[2], arrow_bgr[1], arrow_bgr[0])
        text_rgb = (text_bgr[2], text_bgr[1], text_bgr[0])

        # Calculate arrow dimensions based on frame size
        base_dim = min(h, w)
        arrow_head_h = int(base_dim * 0.06 * arrow_size)
        arrow_head_w = int(base_dim * 0.04 * arrow_size)
        arrow_shaft_w = int(base_dim * 0.008 * arrow_size)
        arrow_shaft_h = int(base_dim * 0.12 * arrow_len)
        gap = int(base_dim * 0.01) + int(offset_y)

        # Arrow tip points at the person's top
        person_top_y = int(cy)
        if bbox is not None:
            person_top_y = int(bbox[1])

        tip_y = person_top_y - gap
        tip_x = int(cx)

        # Shaft top
        shaft_top_y = tip_y - arrow_head_h - arrow_shaft_h
        shaft_bot_y = tip_y - arrow_head_h

        # Draw on a copy
        result = frame.copy()

        # Draw shaft (vertical line) with slight glow
        cv2.line(result, (tip_x, shaft_top_y), (tip_x, shaft_bot_y),
                 arrow_rgb, arrow_shaft_w + 2, cv2.LINE_AA)
        cv2.line(result, (tip_x, shaft_top_y), (tip_x, shaft_bot_y),
                 arrow_rgb, arrow_shaft_w, cv2.LINE_AA)

        # Draw arrowhead (triangle pointing down) with outline for visibility
        pts = np.array([
            [tip_x, tip_y],
            [tip_x - arrow_head_w // 2, tip_y - arrow_head_h],
            [tip_x + arrow_head_w // 2, tip_y - arrow_head_h]
        ], dtype=np.int32)
        # Dark outline for contrast on any background
        cv2.polylines(result, [pts], True, (0, 0, 0), max(2, arrow_shaft_w), cv2.LINE_AA)
        cv2.fillPoly(result, [pts], arrow_rgb, cv2.LINE_AA)

        # Draw name label if mode is arrow_and_name and name is not empty
        if mode == 'arrow_and_name' and name.strip():
            font_scale = 0.7 * text_size
            thickness = max(1, int(2 * text_size))
            (tw, th), baseline = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)

            text_x = tip_x - tw // 2
            text_y = shaft_top_y - int(base_dim * 0.015)

            # Background rectangle with rounded look
            pad = int(base_dim * 0.01)
            cv2.rectangle(result,
                          (text_x - pad, text_y - th - pad),
                          (text_x + tw + pad, text_y + pad),
                          (0, 0, 0), -1, cv2.LINE_AA)
            cv2.rectangle(result,
                          (text_x - pad, text_y - th - pad),
                          (text_x + tw + pad, text_y + pad),
                          text_rgb, max(2, int(2 * text_size)), cv2.LINE_AA)

            # Text with dark outline for readability
            cv2.putText(result, name, (text_x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0),
                        thickness + 2, cv2.LINE_AA)
            cv2.putText(result, name, (text_x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_rgb,
                        thickness, cv2.LINE_AA)

        return result
