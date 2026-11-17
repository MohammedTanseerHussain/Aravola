"""Template matching and subject tracking across frames.

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


class TrackingImplMixin:
    """Template matching and subject tracking across frames."""

    def _anchor_tracking_at(self, item, frame, center, bbox, is_correction):
        """(Re)anchor the tracking chain at the CURRENT frame with the
        given center/bbox.

        If `is_correction`: this is a manual fix to an ALREADY-selected,
        already-tracked object. Keyframes BEFORE this frame are left
        untouched -- whatever arrow position earlier frames already have
        stays exactly as it was -- while keyframes AT OR AFTER this frame
        are cleared, since they were derived from the trajectory this
        correction is fixing, and the chain needs to continue fresh from
        the corrected point onward.

        If not a correction (a brand new selection of a person/object):
        the entire tracking history is discarded and replaced with just
        this one keyframe, since carrying over history from a DIFFERENT
        previous selection would corrupt the new one's tracking.

        Returns the frame_idx this was anchored at."""
        frame_idx0 = int(self.playhead_t.get() * 30)
        existing = item.get('effect_tracking_keyframes', {}) if is_correction else {}
        if is_correction:
            existing = {k: v for k, v in existing.items() if int(k) < frame_idx0}
        existing[str(frame_idx0)] = {
            'center': center,
            'bbox': bbox,
            'time': self.playhead_t.get(),
            'ref_w': frame.shape[1],
            'ref_h': frame.shape[0],
        }
        item['effect_tracking_keyframes'] = existing
        item['effect_track_miss_streak'] = 0
        item['effect_last_match_frame_idx'] = frame_idx0
        item['effect_track_template_patch'], item['effect_track_template_inner_offset'] = self._extract_track_template_patch(frame, bbox)
        item['effect_track_template_ref_wh'] = (frame.shape[1], frame.shape[0])
        return frame_idx0

    def _extract_track_template_patch(self, frame, bbox, pad_frac=0.6):
        """Grab a grayscale patch around `bbox`, expanded by `pad_frac` on
        each side, to use as the local tracking template.

        The padding matters: a tight crop of a sports jersey is close to
        a single flat color, which carries almost no information to tell
        two similarly-dressed players apart. The area immediately around
        the person -- the specific patch of grass, a line marking, a
        shadow -- is far more spatially unique, and correlating against
        that context is what actually anchors the match to the right
        individual instead of any similarly-colored blob nearby.

        Returns (patch_gray, inner_offset), where inner_offset =
        (ox, oy, obw, obh) locates the ORIGINAL (unpadded) bbox within
        the returned patch, so a later match on the padded patch can be
        converted back to the object's own tight bbox. Returns (None,
        None) if the region is degenerate."""
        try:
            x, y, bw, bh = bbox
            h, w = frame.shape[:2]
            pad_x = max(4, int(bw * pad_frac))
            pad_y = max(4, int(bh * pad_frac))
            x0, y0 = max(0, int(x - pad_x)), max(0, int(y - pad_y))
            x1, y1 = min(w, int(x + bw + pad_x)), min(h, int(y + bh + pad_y))
            if x1 - x0 < 6 or y1 - y0 < 6:
                return None, None
            patch = frame[y0:y1, x0:x1]
            gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY) if patch.ndim == 3 else patch
            inner_offset = (int(x - x0), int(y - y0), int(bw), int(bh))
            return gray.copy(), inner_offset
        except Exception as _e:
            print("[LOCAL-TRACK] template extraction error:", _e)
            return None, None

    def _template_track_local(self, frame, template_gray, search_center, search_radius, upsample=3):
        """Locate `template_gray` inside a SMALL window around
        `search_center` (cx, cy) using normalized cross-correlation, biased
        toward the window's center. Without that bias, a same-coloured
        neighbour who has drifted into the edge of the (small) search
        window can still occasionally out-correlate the actual tracked
        object if lighting/pose happens to line up better there -- the
        bias keeps the match "pinned" to where the object is predicted to
        be unless the edge candidate is a MUCH better match, not just a
        marginally better one.

        `upsample`: both the window and template are enlarged by this
        factor (cubic interpolation) before correlating. For a small
        object (a dozen-odd px), the native pixel grid only offers that
        many discrete candidate positions -- upsampling recovers
        meaningfully finer (near sub-pixel) localization instead of being
        capped by raw pixel resolution. The returned bbox is in ORIGINAL
        (non-upsampled) pixel coordinates.

        Returns {'bbox': (x,y,w,h), 'score': float} or None.
        `score` is the RAW (unbiased) correlation, roughly [-1, 1]."""
        if template_gray is None or template_gray.size == 0:
            return None
        th, tw = template_gray.shape[:2]
        if th < 3 or tw < 3:
            return None
        h, w = frame.shape[:2]
        cx, cy = search_center
        win_half_w = int(tw / 2 + search_radius)
        win_half_h = int(th / 2 + search_radius)
        x0 = max(0, int(cx - win_half_w))
        y0 = max(0, int(cy - win_half_h))
        x1 = min(w, int(cx + win_half_w))
        y1 = min(h, int(cy + win_half_h))
        if x1 - x0 < tw or y1 - y0 < th:
            return None
        try:
            window = frame[y0:y1, x0:x1]
            window_gray = cv2.cvtColor(window, cv2.COLOR_RGB2GRAY) if window.ndim == 3 else window

            up = max(1, int(upsample))
            if up > 1:
                window_up = cv2.resize(window_gray, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
                template_up = cv2.resize(template_gray, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
            else:
                window_up, template_up = window_gray, template_gray
            tuh, tuw = template_up.shape[:2]
            if window_up.shape[0] < tuh or window_up.shape[1] < tuw:
                window_up, template_up, up = window_gray, template_gray, 1
                tuh, tuw = template_up.shape[:2]

            result = cv2.matchTemplate(window_up, template_up, cv2.TM_CCOEFF_NORMED)
            rh, rw = result.shape
            # result[i, j] is the match score for the (upsampled) template's
            # top-left placed at upsampled-window-local (j, i). Bias toward
            # the predicted top-left position (also in upsampled units)
            # before picking the winner -- but scale the bias so its max
            # penalty (at the window's edge) is a fixed, modest amount
            # regardless of window size. A flat per-pixel rate is fine for
            # a large window, but for the small windows used on small
            # objects (the common case here) it becomes strong enough to
            # outweigh genuine motion entirely, punishing the object for
            # actually moving and anchoring the tracker to one spot instead
            # of following it.
            pred_x = ((cx - x0) - tw / 2.0) * up
            pred_y = ((cy - y0) - th / 2.0) * up
            yy, xx = np.mgrid[0:rh, 0:rw]
            dist = np.sqrt((xx - pred_x) ** 2 + (yy - pred_y) ** 2) / up
            bias_coeff = 0.10 / max(search_radius, 1)
            biased = result - bias_coeff * dist
            my, mx = np.unravel_index(np.argmax(biased), biased.shape)
            score = float(result[my, mx])
            bbox = (int(round(x0 + mx / up)), int(round(y0 + my / up)), tw, th)
            return {'bbox': bbox, 'score': score}
        except Exception as _e:
            print("[LOCAL-TRACK] template match error:", _e)
            return None

    def _verify_local_context(self, item, frame, position, radius=14):
        """Quick correlation check: does the immediate surroundings at
        `position` (cx, cy) actually match the stored tracking patch?

        Used as a VETO on Stage 2 (whole-frame YOLO + appearance-histogram)
        matches. A colour histogram on a tiny, near-flat-coloured crop
        can't reliably tell two similarly-dressed people apart -- that's
        exactly what let Stage 2 occasionally lock onto the wrong nearby
        person on the rare frame where Stage 1's tight local search missed
        (motion blur, a fast movement, brief occlusion) and control fell
        back to the weaker whole-frame path. This re-checks the candidate
        Stage 2 picked against the same context-rich patch Stage 1 uses --
        the specific surrounding grass/lines/shadows at the WRONG person's
        position generally won't correlate well even when their jersey
        colour does.

        The radius here is deliberately a bit looser than Stage 1's own
        search: a YOLO detection's center is coarser than a correlation
        match, so a genuinely correct Stage 2 candidate can legitimately
        sit a few pixels from the "ideal" spot -- too tight a radius here
        would fail correct matches, not just wrong ones, causing the arrow
        to disappear more than it should.

        Returns a correlation score in roughly [-1, 1], or None if there's
        no stored patch to check against (e.g. right after selection)."""
        template_patch = item.get('effect_track_template_patch')
        if template_patch is None:
            return None
        h, w = frame.shape[:2]
        patch_ref_w, patch_ref_h = item.get('effect_track_template_ref_wh', (None, None))
        match_patch = template_patch
        if patch_ref_w and patch_ref_h and (patch_ref_w != w or patch_ref_h != h):
            psx, psy = w / patch_ref_w, h / patch_ref_h
            new_tw = max(3, int(template_patch.shape[1] * psx))
            new_th = max(3, int(template_patch.shape[0] * psy))
            try:
                match_patch = cv2.resize(template_patch, (new_tw, new_th), interpolation=cv2.INTER_LINEAR)
            except Exception:
                match_patch = template_patch
        hit = self._template_track_local(frame, match_patch, position, search_radius=radius, upsample=3)
        return hit['score'] if hit else None

    def _maybe_refresh_track_template(self, item, frame, bbox, score=None):
        """Adaptively refresh the local-tracking patch on confident matches
        so it keeps up with gradual pose/scale/lighting changes. Only
        refreshes on a strong score so a marginal/uncertain match can't
        slowly drag the template toward the wrong object."""
        if score is not None and score < 0.55:
            return
        new_patch, new_offset = self._extract_track_template_patch(frame, bbox)
        if new_patch is not None:
            item['effect_track_template_patch'] = new_patch
            item['effect_track_template_inner_offset'] = new_offset
            item['effect_track_template_ref_wh'] = (frame.shape[1], frame.shape[0])

    def _get_person_appearance(self, frame, bbox):
        """Extract appearance features of an object from a bounding box.
        Returns a dict with color histogram, edge pattern, face features (if person),
        and spatial info used for matching across frames."""
        h, w = frame.shape[:2]
        x, y, bw, bh = bbox
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(w, x + bw)
        y1 = min(h, y + bh)
        if x1 - x0 < 5 or y1 - y0 < 5:
            return None

        obj_region = frame[y0:y1, x0:x1]

        # --- Face detection inside the object bbox (works for people, optional) ---
        face_hist = None
        face_rect = None
        face_embedding = None
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            face_cascade = cv2.CascadeClassifier(_HAAR_CASCADE_PATH)
            faces = face_cascade.detectMultiScale(gray[y0:y1, x0:x1], 1.1, 4, minSize=(20, 20))
            if len(faces) > 0:
                fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                face_rect = (x0 + fx, y0 + fy, fw, fh)
                face_region = frame[y0 + fy:y0 + fy + fh, x0 + fx:x0 + fx + fw]
                if face_region.size > 0:
                    hsv_face = cv2.cvtColor(face_region, cv2.COLOR_RGB2HSV)
                    face_hist = cv2.calcHist([hsv_face], [0, 1, 2], None, [16, 8, 4], [0, 180, 0, 256, 0, 256])
                    cv2.normalize(face_hist, face_hist, 0, 1, cv2.NORM_MINMAX)
                    gray_face = cv2.cvtColor(face_region, cv2.COLOR_RGB2GRAY)
                    face_embedding = cv2.resize(gray_face, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        except Exception:
            pass

        # --- Full object color histogram (works for ANY object: ball, car, person, etc.) ---
        obj_hist = None
        if obj_region.size > 0:
            hsv_obj = cv2.cvtColor(obj_region, cv2.COLOR_RGB2HSV)
            obj_hist = cv2.calcHist([hsv_obj], [0, 1], None, [12, 8], [0, 180, 0, 256])
            cv2.normalize(obj_hist, obj_hist, 0, 1, cv2.NORM_MINMAX)

        # --- Edge shape template ---
        gray_obj = cv2.cvtColor(obj_region, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray_obj, 50, 150)
        edge_template = cv2.resize(edges, (48, 80), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

        return {
            'face_hist': face_hist,
            'face_embedding': face_embedding,
            'face_rect': face_rect,
            'body_hist': obj_hist,
            'edge_template': edge_template,
            'bbox': bbox,
            'center': (y0 + (y1 - y0) // 2, x0 + (x1 - x0) // 2),
            'size': (bw, bh),
            'area': bw * bh,
        }

    def _match_person_to_template(self, frame, candidates, template, last_center=None, face_buffer=None, max_spatial_dist=None):
        """Match detected person candidates against stored appearance template.
        Returns the best matching index and its confidence score.
        last_center: (cy, cx) of the person's position in the previous frame,
        used for spatial continuity — rejects matches that jump too far.
        max_spatial_dist: override for how far (in px) a candidate may be
        from last_center and still be considered. Callers should pass a
        SIZE-AWARE value — a fixed fraction of the whole frame is far too
        permissive in a wide shot with many small, similarly-dressed
        subjects (e.g. a football broadcast angle): it lets a same-team
        player on the other side of the pitch outscore the actual tracked
        person just by having a marginally better colour-histogram match on
        a tiny, low-detail crop.
        face_buffer: list of past face appearance samples for multi-scale matching."""
        if template is None or not candidates:
            return -1, 0.0

        if face_buffer is None:
            face_buffer = []

        h, w = frame.shape[:2]
        if max_spatial_dist is None:
            max_spatial_dist = max(h, w) * 0.4

        best_idx = -1
        best_score = -1.0

        for i, person in enumerate(candidates):
            app = self._get_person_appearance(frame, person['bbox'])
            if app is None:
                continue

            score = 0.0
            n_features = 0
            feature_scores = []

            # Face embedding: match against ALL buffer entries, take best
            if app.get('face_embedding') is not None:
                best_face_emb_sim = -1.0
                # Check main template
                if template.get('face_embedding') is not None:
                    t_fe = template['face_embedding'].flatten()
                    c_fe = app['face_embedding'].flatten()
                    sim = float(np.sum(t_fe * c_fe)) / max(1.0, float(np.sqrt(np.sum(t_fe**2) * np.sum(c_fe**2))))
                    best_face_emb_sim = max(best_face_emb_sim, sim)
                # Check all buffer entries (different scales/angles)
                for buf_entry in face_buffer:
                    if buf_entry.get('face_embedding') is not None:
                        t_fe = buf_entry['face_embedding'].flatten()
                        c_fe = app['face_embedding'].flatten()
                        sim = float(np.sum(t_fe * c_fe)) / max(1.0, float(np.sqrt(np.sum(t_fe**2) * np.sum(c_fe**2))))
                        best_face_emb_sim = max(best_face_emb_sim, sim)
                if best_face_emb_sim >= 0:
                    feature_scores.append(('face_emb', best_face_emb_sim, 0.40))
                    n_features += 1

            # Face histogram: match against ALL buffer entries, take best
            if app.get('face_hist') is not None:
                best_face_sim = -1.0
                if template.get('face_hist') is not None:
                    sim = cv2.compareHist(
                        template['face_hist'].astype(np.float32),
                        app['face_hist'].astype(np.float32),
                        cv2.HISTCMP_CORREL)
                    best_face_sim = max(best_face_sim, sim)
                for buf_entry in face_buffer:
                    if buf_entry.get('face_hist') is not None:
                        sim = cv2.compareHist(
                            buf_entry['face_hist'].astype(np.float32),
                            app['face_hist'].astype(np.float32),
                            cv2.HISTCMP_CORREL)
                        best_face_sim = max(best_face_sim, sim)
                if best_face_sim >= 0:
                    feature_scores.append(('face', best_face_sim, 0.25))
                    n_features += 1

            # Body histogram similarity
            if template.get('body_hist') is not None and app.get('body_hist') is not None:
                body_sim = cv2.compareHist(
                    template['body_hist'].astype(np.float32),
                    app['body_hist'].astype(np.float32),
                    cv2.HISTCMP_CORREL)
                feature_scores.append(('body', body_sim, 0.20))
                n_features += 1

            # Edge template similarity
            if template.get('edge_template') is not None and app.get('edge_template') is not None:
                t_edges = template['edge_template']
                c_edges = app['edge_template']
                edge_sim = float(np.sum(t_edges * c_edges)) / max(1.0, float(np.sqrt(np.sum(t_edges**2) * np.sum(c_edges**2))))
                feature_scores.append(('edge', edge_sim, 0.15))
                n_features += 1

            if n_features < 1:
                continue

            total_weight = sum(w for _, _, w in feature_scores)
            for _, sim, weight in feature_scores:
                score += sim * (weight / total_weight)

            # Spatial continuity bonus: closer to prediction = higher score
            if last_center is not None:
                pcx, pcy = person['center'][1], person['center'][0]
                dy = last_center[0] - pcy
                dx = last_center[1] - pcx
                dist = (dx ** 2 + dy ** 2) ** 0.5
                if dist > max_spatial_dist:
                    continue
                spatial_bonus = 0.6 * (1.0 - dist / max_spatial_dist)
                score += spatial_bonus

            if score > best_score:
                best_score = score
                best_idx = i

        return best_idx, best_score
