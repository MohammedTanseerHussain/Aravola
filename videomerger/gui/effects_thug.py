"""Thug-life glasses, chain and cap rendering.

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


class EffectsThugMixin:
    """Thug-life glasses, chain and cap rendering."""

    def _load_thug_asset(self, key):
        """Load (and cache) a thug-life accessory from ``assets/accessories``.

        Valid keys: 'glasses', 'chain' (pixel-art), 'glasses_real',
        'chain_real', 'cap' (photographic-style).
        """
        if not hasattr(self, "_thug_asset_cache"):
            self._thug_asset_cache = {}
        if key in self._thug_asset_cache:
            return self._thug_asset_cache[key]

        from ..config import CAP, CHAIN_PIXEL, CHAIN_REAL, GLASSES_PIXEL, GLASSES_REAL
        from PIL import Image

        paths = {
            "glasses": GLASSES_PIXEL,
            "chain": CHAIN_PIXEL,
            "glasses_real": GLASSES_REAL,
            "chain_real": CHAIN_REAL,
            "cap": CAP,
        }
        img = None
        path = paths.get(key)
        if path is not None:
            try:
                img = Image.open(path).convert("RGBA")
            except Exception as e:
                print(f"WARNING: failed to load thug-life '{key}' asset: {e}")
        self._thug_asset_cache[key] = img
        return img

    def _draw_thug_glasses(self, width, height, style='pixel'):
        """Return the sunglasses scaled to `width` px wide (native aspect kept).
        style='pixel' uses nearest-neighbour scaling for a crisp 8-bit look;
        style='realistic' uses smooth (LANCZOS) scaling for the photographic asset."""
        if width < 10:
            return None
        src = self._load_thug_asset('glasses_real' if style == 'realistic' else 'glasses')
        if src is None:
            return None
        from PIL import Image
        sw, sh = src.size
        scale = max(width / sw, 0.01)
        new_w = max(1, int(round(sw * scale)))
        new_h = max(1, int(round(sh * scale)))
        resample = Image.LANCZOS if style == 'realistic' else Image.NEAREST
        return src.resize((new_w, new_h), resample)

    def _draw_gold_chain(self, width, height, style='pixel'):
        """Return the gold chain scaled to `width` px wide (native aspect kept).
        style='pixel' uses nearest-neighbour scaling for a crisp 8-bit look;
        style='realistic' uses smooth (LANCZOS) scaling for the photographic asset."""
        if width < 10:
            return None
        src = self._load_thug_asset('chain_real' if style == 'realistic' else 'chain')
        if src is None:
            return None
        from PIL import Image
        sw, sh = src.size
        scale = max(width / sw, 0.01)
        new_w = max(1, int(round(sw * scale)))
        new_h = max(1, int(round(sh * scale)))
        resample = Image.LANCZOS if style == 'realistic' else Image.NEAREST
        return src.resize((new_w, new_h), resample)

    def _draw_thug_cap(self, width, height):
        """Return the flat-brim cap scaled to `width` px wide (native aspect kept)."""
        if width < 10:
            return None
        src = self._load_thug_asset('cap')
        if src is None:
            return None
        from PIL import Image
        sw, sh = src.size
        scale = max(width / sw, 0.01)
        new_w = max(1, int(round(sw * scale)))
        new_h = max(1, int(round(sh * scale)))
        return src.resize((new_w, new_h), Image.LANCZOS)

    def _overlay_at_center(self, frame_np, overlay_pil, center_x, center_y, angle=0, scale=1.0,
                            opacity=1.0, flip_h=False, flip_v=False):
        if overlay_pil is None:
            return frame_np
        from PIL import Image
        if flip_h:
            overlay_pil = overlay_pil.transpose(Image.FLIP_LEFT_RIGHT)
        if flip_v:
            overlay_pil = overlay_pil.transpose(Image.FLIP_TOP_BOTTOM)
        if scale != 1.0:
            sw = max(1, int(round(overlay_pil.width * scale)))
            sh = max(1, int(round(overlay_pil.height * scale)))
            overlay_pil = overlay_pil.resize((sw, sh), Image.NEAREST)
        if angle != 0:
            overlay_pil = overlay_pil.rotate(
                angle, expand=True, resample=Image.BICUBIC,
                center=(overlay_pil.width // 2, overlay_pil.height // 2),
                fillcolor=(0, 0, 0, 0)
            )
        if opacity < 1.0:
            opacity = max(0.0, min(1.0, opacity))
            arr = np.array(overlay_pil)
            arr[..., 3] = (arr[..., 3].astype(np.float32) * opacity).astype(np.uint8)
            overlay_pil = Image.fromarray(arr, 'RGBA')
        x = int(center_x - overlay_pil.width // 2)
        y = int(center_y - overlay_pil.height // 2)
        frame_pil = Image.fromarray(frame_np).convert('RGBA')
        frame_pil.paste(overlay_pil, (x, y), overlay_pil)
        return np.array(frame_pil.convert('RGB'))

    def _thug_entry_transform(self, entry, p, base_w, base_h):
        """Given an entry style and animation progress p in [0,1] (0=start,
        1=settled), return (dx, dy, extra_angle, scale) offsets to layer on
        top of an accessory's resting position/size. dx/dy are directional
        offsets away from the resting spot (positive = right/down)."""
        eased = self._thug_ease_out_back(p)
        remaining = 1.0 - min(eased, 1.0)
        settle = min(eased, 1.0)
        if entry == 'left':
            dx = remaining * (base_w * 3.0 + 140)
            dy = 0.0
            extra_angle = remaining * -300.0
            scale = max(0.05, 0.3 + 0.7 * settle)
        elif entry == 'right':
            dx = -remaining * (base_w * 3.0 + 140)
            dy = 0.0
            extra_angle = remaining * 300.0
            scale = max(0.05, 0.3 + 0.7 * settle)
        elif entry == 'bottom':
            dx = 0.0
            dy = remaining * (base_h * 4.0 + 100)
            extra_angle = remaining * 300.0
            scale = max(0.05, 0.3 + 0.7 * settle)
        elif entry == 'rush':
            dx = 0.0
            dy = 0.0
            extra_angle = 0.0
            scale = max(0.05, 0.06 + 0.94 * settle)
        elif entry == 'bounce':
            bounced = self._thug_ease_out_bounce(p)
            dx = 0.0
            dy = (1.0 - bounced) * (base_h * 4.0 + 100)
            extra_angle = 0.0
            scale = max(0.1, 0.4 + 0.6 * min(bounced, 1.0))
        else:  # 'top' (classic drop-and-spin)
            dx = 0.0
            dy = remaining * (base_h * 4.0 + 60)
            extra_angle = remaining * -520.0
            scale = max(0.05, 0.25 + 0.75 * settle)
        return dx, dy, extra_angle, scale

    def _find_eye_center(self, frame, head_cy, head_cx, face_w, face_h):
        h, w = frame.shape[:2]
        face_y0 = head_cy - face_h // 2
        face_x0 = head_cx - face_w // 2
        # Eyes sit in the upper-middle band of a Haar face box. Excluding the
        # hairline/forehead sliver at the very top (and the nose/mouth/chin
        # below) stops eyebrows or hair texture from being mistaken for eyes.
        roi_y0 = max(0, face_y0 + int(face_h * 0.12))
        roi_y1 = min(h, face_y0 + int(face_h * 0.62))
        roi_x0 = max(0, face_x0)
        roi_x1 = min(w, face_x0 + face_w)
        if roi_y1 - roi_y0 < 10 or roi_x1 - roi_x0 < 10:
            return None
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            face_roi = gray[roi_y0:roi_y1, roi_x0:roi_x1]
            eye_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_eye.xml")
            if eye_cascade.empty():
                return None
            eyes = eye_cascade.detectMultiScale(face_roi, 1.1, 4, minSize=(6, 6))
            if len(eyes) >= 2:
                eyes = sorted(eyes, key=lambda e: e[0])
                left = eyes[0]
                right = eyes[-1]
                eye_dist = abs((right[0] + right[2] // 2) - (left[0] + left[2] // 2))
                eye_cx = (left[0] + left[2] // 2 + right[0] + right[2] // 2) // 2 + roi_x0
                eye_cy = (left[1] + left[3] // 2 + right[1] + right[3] // 2) // 2 + roi_y0
                left_cy = left[1] + left[3] // 2
                right_cy = right[1] + right[3] // 2
                left_cx = left[0] + left[2] // 2
                right_cx = right[0] + right[2] // 2
                roll_deg = math.degrees(math.atan2(right_cy - left_cy, right_cx - left_cx))
                # Sanity-check the result against the face box it came from —
                # a stray detection (eyebrow, hair shadow, nostril) tends to
                # sit too high/low or be an implausible distance apart.
                rel_y = (eye_cy - face_y0) / max(face_h, 1)
                if not (0.15 <= rel_y <= 0.65):
                    return None
                if not (0.25 * face_w <= eye_dist <= 0.95 * face_w):
                    return None
                return eye_cy, eye_cx, max(eye_dist, face_w // 4), roll_deg
        except Exception:
            pass
        return None

    def _find_thug_face_box(self, frame, search_bbox=None):
        """Haar-cascade frontal face detection over the FULL frame — returns
        (fx, fy, fw, fh) for the best candidate, or None. Detection always runs
        on the whole image (not a tight crop) because for wide poses — arms
        raised overhead, etc. — a bbox/silhouette crop is mostly background,
        and equalising/searching just that region is *less* reliable than the
        full photo. When `search_bbox` (x, y, w, h) is given, it's used only to
        prefer the candidate face located inside that person's region — so a
        blurry crowd/background face isn't picked over the actual subject —
        falling back to the largest face overall if none fall inside it."""
        h, w = frame.shape[:2]
        try:
            gray_full = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            min_dim = max(20, min(h, w) // 12)

            def run_cascades(gray_img):
                found = []
                for cascade_path in (_HAAR_CASCADE_PATH,):
                    face_cascade = cv2.CascadeClassifier(cascade_path)
                    if face_cascade.empty():
                        continue
                    faces = face_cascade.detectMultiScale(
                        gray_img, scaleFactor=1.05, minNeighbors=4, minSize=(min_dim, min_dim))
                    found.extend(tuple(int(v) for v in f) for f in faces)
                return found

            candidates = run_cascades(cv2.equalizeHist(gray_full))
            if not candidates:
                candidates = run_cascades(gray_full)
            if not candidates:
                return None

            if search_bbox is not None:
                bx, by, bw, bh = search_bbox
                pad_x, pad_y = int(bw * 0.2), int(bh * 0.2)
                x0, y0 = bx - pad_x, by - pad_y
                x1, y1 = bx + bw + pad_x, by + bh + pad_y
                inside = [c for c in candidates
                          if x0 <= (c[0] + c[2] / 2) <= x1 and y0 <= (c[1] + c[3] / 2) <= y1]
                if inside:
                    candidates = inside

            return max(candidates, key=lambda f: f[2] * f[3])
        except Exception:
            return None

    @staticmethod
    def _thug_ease_out_back(p):
        c1, c3 = 1.70158, 2.70158
        p = min(max(p, 0.0), 1.0)
        return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2

    @staticmethod
    def _thug_ease_out_bounce(p):
        n1, d1 = 7.5625, 2.75
        p = min(max(p, 0.0), 1.0)
        if p < 1 / d1:
            return n1 * p * p
        elif p < 2 / d1:
            p -= 1.5 / d1
            return n1 * p * p + 0.75
        elif p < 2.5 / d1:
            p -= 2.25 / d1
            return n1 * p * p + 0.9375
        else:
            p -= 2.625 / d1
            return n1 * p * p + 0.984375

    def _create_thug_life_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, bbox=None, drawn_edges=None, clip_t=0.0,
                                  style='pixel', entry='top', cap_enabled=False,
                                  glasses_override=None, chain_override=None, cap_override=None):
        h, w = frame.shape[:2]
        base = original_mask if original_mask is not None else mask
        mask_bool = (base > 0.3) if base is not None else np.zeros((h, w), dtype=bool)

        # Restrict to the selected person's region when we have one, so a
        # raised arm, a bystander, or crowd in the background can't get
        # mistaken for the subject.
        if bbox is not None:
            bx, by, bw, bh = bbox
            region = np.zeros((h, w), dtype=bool)
            region[max(0, by):min(h, by + bh), max(0, bx):min(w, bx + bw)] = True
            mask_bool = mask_bool & region

        ys, xs = np.where(mask_bool)
        if len(ys) > 10:
            y_top, y_bot = int(ys.min()), int(ys.max())
            person_h = max(y_bot - y_top, 1)
            person_w = max(int(xs.max()) - int(xs.min()), 1)
            median_x = int(np.median(xs))
        elif bbox is not None:
            bx, by, bw, bh = bbox
            y_top, y_bot = by, by + bh
            person_h, person_w = max(bh, 1), max(bw, 1)
            median_x = bx + bw // 2
        else:
            y_top, y_bot = 0, h
            person_h, person_w = h, w
            median_x = w // 2

        # ── Locate the face precisely so glasses fit the actual eyes. Search is
        # restricted to the subject's own silhouette so a face in a blurry
        # crowd/background can't be picked up instead. ──
        if bbox is not None:
            search_box = bbox
        elif len(ys) > 10:
            search_box = (int(xs.min()), y_top, person_w, person_h)
        else:
            search_box = None
        face_box = self._find_thug_face_box(frame, search_bbox=search_box)

        if face_box is not None:
            fx, fy, fw, fh = face_box
            head_cy, head_cx = fy + fh // 2, fx + fw // 2
            eyes = self._find_eye_center(frame, head_cy, head_cx, fw, fh)
            if eyes is not None:
                eye_cy, eye_cx, eye_dist, roll_deg = eyes
                eye_y = eye_cy
                glass_w = int(eye_dist * 2.4)          # span both eyes + temples
                base_angle = max(-25.0, min(25.0, roll_deg))  # follow head tilt, clamped to a sane range
            else:
                eye_y = fy + int(fh * 0.42)             # typical eye line on a face
                eye_cx = fx + fw // 2
                glass_w = int(fw * 1.05)
                base_angle = 0.0
            neck_cx = eye_cx
            neck_y = (fy + fh) + int(fh * 0.35)         # chin + neck offset
            cap_cx = eye_cx
            cap_anchor_y = fy + int(fh * 0.15)          # brim sits just above the eyebrows
        else:
            # No face found (steep angle, motion blur, hand over face, etc.) —
            # fall back to the body silhouette, but stay in a narrow column
            # centered on the torso's median so raised/outstretched arms can't
            # be mistaken for the head (their pixels sit outside this band).
            band_half = max(int(person_w * 0.16), 35)
            band_x0, band_x1 = median_x - band_half, median_x + band_half
            in_band = (xs >= band_x0) & (xs <= band_x1)
            band_rows = np.unique(ys[in_band]) if np.any(in_band) else np.array([], dtype=int)
            head_top = int(band_rows.min()) if len(band_rows) > 5 else y_top

            scan_bottom = min(y_bot, head_top + max(int(person_h * 0.30), 1))
            widths = []
            for row_y in range(head_top, scan_bottom):
                row_pixels = xs[(ys == row_y) & in_band]
                if len(row_pixels) >= 3:
                    widths.append(row_pixels.max() - row_pixels.min())
            head_w_est = int(np.median(widths)) if widths else max(int(w * 0.09), 50)
            head_w_est = max(head_w_est, 50)
            head_h_est = int(head_w_est * 1.3)          # typical face width:height ratio

            eye_cx = median_x
            eye_y = head_top + int(head_h_est * 0.45)   # eyes ~45% down from crown
            neck_cx = eye_cx
            neck_y = head_top + int(head_h_est * 1.15)  # just below the chin
            glass_w = int(head_w_est * 1.05)
            base_angle = 0.0
            cap_cx = eye_cx
            cap_anchor_y = head_top

        glass_w = max(glass_w, 60)
        chain_w = int(glass_w * (1.9 if style == 'pixel' else 1.15))
        cap_w = int(glass_w * 1.5)

        glasses_img = self._draw_thug_glasses(glass_w, glass_w, style=style)
        chain_img = self._draw_gold_chain(chain_w, chain_w, style=style)
        cap_img = self._draw_thug_cap(cap_w, cap_w) if cap_enabled else None
        glass_h = glasses_img.height if glasses_img is not None else int(glass_w * 0.2)
        chain_h = chain_img.height if chain_img is not None else int(chain_w * 0.84)
        cap_h = cap_img.height if cap_img is not None else int(cap_w * 0.6)
        cap_cy = cap_anchor_y - cap_h // 2

        result = frame.copy()
        t = max(0.0, float(clip_t))

        def anim(local_t, anim_dur, base_w, base_h):
            p = min(max(local_t, 0.0) / anim_dur, 1.0) if anim_dur > 0 else 1.0
            adx, ady, aangle, ascale = self._thug_entry_transform(entry, p, base_w, base_h)
            aopacity = min(max(local_t, 0.0) / (anim_dur * 0.4), 1.0) if local_t > 0 else 0.0
            return adx, ady, aangle, ascale, aopacity

        def with_override(cx, cy, angle, scale, override):
            fh_, fv_ = False, False
            if override:
                cx = cx + override.get('dx', 0.0)
                cy = cy + override.get('dy', 0.0)
                angle = angle + override.get('rotation', 0.0)
                scale = scale * override.get('scale', 1.0)
                fh_ = bool(override.get('flip_h', False))
                fv_ = bool(override.get('flip_v', False))
            return cx, cy, angle, scale, fh_, fv_

        # ── Cap: leads the entrance (if enabled) ──
        if cap_img is not None:
            cdx, cdy, cangle, cscale, copac = anim(t, 0.5, cap_w, cap_h)
            cx, cy, cang, csc, cfh, cfv = with_override(
                cap_cx + cdx, cap_cy + cdy, base_angle + cangle, cscale, cap_override)
            result = self._overlay_at_center(result, cap_img, cx, cy, angle=cang, scale=csc,
                                              opacity=copac, flip_h=cfh, flip_v=cfv)

        # ── Glasses: land exactly on the eyes ──
        gdx, gdy, gangle, gscale, gopac = anim(t - 0.10, 0.5, glass_w, glass_h)
        gx, gy, gang, gsc, gfh, gfv = with_override(
            eye_cx + gdx, eye_y + gdy, base_angle + gangle, gscale, glasses_override)
        if glasses_img is not None:
            result = self._overlay_at_center(result, glasses_img, gx, gy, angle=gang, scale=gsc,
                                              opacity=gopac, flip_h=gfh, flip_v=gfv)

        # ── Chain: settles around the neck last ──
        chdx, chdy, changle, chscale, chopac = anim(t - 0.22, 0.55, chain_w, chain_h)
        chx, chy, chang, chsc, chfh, chfv = with_override(
            neck_cx + chdx, neck_y + chdy, base_angle + changle, chscale, chain_override)
        if chain_img is not None and chopac > 0:
            result = self._overlay_at_center(result, chain_img, chx, chy, angle=chang, scale=chsc,
                                              opacity=chopac, flip_h=chfh, flip_v=chfv)

        return result

    def apply_thug_life_effect(self, frame, item, t):
        if not item.get('effect_thug_life_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame
        selected_id = int(item.get('effect_selected_person', -1))
        if selected_id >= 0 or selected_id == -2:
            mask = self._get_selected_person_mask(frame, item, t=t)
        else:
            mask = self._get_mediapipe_mask(frame)
            if mask is None:
                persons = self._detect_all_persons(frame)
                if persons:
                    cy_mid, cx_mid = h // 2, w // 2
                    best = min(persons, key=lambda p: (
                        (p['center'][0] - cy_mid) ** 2 + (p['center'][1] - cx_mid) ** 2))
                    mask = self._generate_mask_from_bbox(frame, best['bbox'])
        if mask is None or mask.max() < 0.01:
            return frame
        if mask.shape[:2] != (h, w):
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
        original_mask = mask.copy()
        bbox = None
        if selected_id >= 0:
            yolo_persons = self._yolo_track(frame)
            if yolo_persons:
                for p in yolo_persons:
                    if p['id'] == selected_id:
                        bbox = p['bbox']
                        break
        result = self._create_thug_life_effect(
            frame, mask, None, None, 0, 0, 1.0, original_mask, bbox=bbox, clip_t=t,
            style=item.get('thug_style', 'realistic'),
            entry=item.get('thug_entry', 'top'),
            cap_enabled=item.get('thug_cap_enabled', True),
            glasses_override=item.get('thug_glasses_override'),
            chain_override=item.get('thug_chain_override'),
            cap_override=item.get('thug_cap_override'))
        return result
