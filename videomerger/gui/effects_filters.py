"""Colour-filter application.

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


class EffectsFiltersMixin:
    """Colour-filter application."""

    def apply_color_filter(self, frame, style="Cinematic Warm", intensity=1.0,
                           warmth=0.5, saturation=1.0, fade_blacks=0.15):
        """Apply a color grading filter to a numpy RGB frame.
        Returns the filtered frame as uint8."""

        def _draw_line(r0, c0, r1, c1, max_r, max_c):
            """Bresenham's line algorithm - returns (rows, cols) arrays."""
            rows = []
            cols = []
            dr = abs(r1 - r0)
            dc = abs(c1 - c0)
            sr = 1 if r0 < r1 else -1
            sc = 1 if c0 < c1 else -1
            err = dr - dc
            r, c = r0, c0
            while True:
                if 0 <= r < max_r and 0 <= c < max_c:
                    rows.append(r)
                    cols.append(c)
                if r == r1 and c == c1:
                    break
                e2 = 2 * err
                if e2 > -dc:
                    err -= dc
                    r += sr
                if e2 < dr:
                    err += dr
                    c += sc
            return np.array(rows, dtype=np.intp), np.array(cols, dtype=np.intp)
        if intensity <= 0:
            return frame
        f = frame.astype(np.float32)
        h, w = f.shape[:2]

        r, g, b = f[:,:,0], f[:,:,1], f[:,:,2]
        lum = 0.299 * r + 0.587 * g + 0.114 * b

        if style == "Cinematic Warm":
            # Based on the reference image: strong warm amber
            # Shadows: R+20%, G+5%, B-30%
            # Midtones: R+25%, G+5%, B-45%
            # Highlights: R+10%, G+5%, B-20%
            shadow_mask = np.clip(1.0 - lum / 85.0, 0, 1)
            mid_mask = np.exp(-((lum - 128)**2) / (2 * 50**2))
            high_mask = np.clip((lum - 170) / 85.0, 0, 1)

            r += (shadow_mask * 50 + mid_mask * 65 + high_mask * 25) * warmth
            g += (shadow_mask * 10 + mid_mask * 12 + high_mask * 10) * warmth
            b -= (shadow_mask * 80 + mid_mask * 115 + high_mask * 50) * warmth

        elif style == "Golden Hour":
            r += 30 * warmth
            g += 15 * warmth
            b -= 40 * warmth
            # Soft glow
            blur = cv2.GaussianBlur(f, (0, 0), 15)
            f = f * 0.7 + blur * 0.3

        elif style == "Vintage Film":
            r = r * 0.9 + 20
            g = g * 0.85 + 10
            b = b * 0.8 + 5
            # Lift blacks
            r = r * 0.85 + 30
            g = g * 0.85 + 25
            b = b * 0.85 + 20

        elif style == "Vintage Cam":
            # Keep original colors, add light leaks from corners + dark vignette
            Y, X = np.ogrid[:h, :w]

            # ── Light leaks from each corner (colored overlays) ──
            # Top-right: warm yellow/orange
            tr_x = np.clip(1.0 - X.astype(np.float32) / (w * 0.7), 0, 1)
            tr_y = np.clip(Y.astype(np.float32) / (h * 0.7), 0, 1)
            tr_mask = (tr_x * tr_y) ** 1.5
            r += tr_mask * 120 * warmth
            g += tr_mask * 50 * warmth
            b -= tr_mask * 20 * warmth

            # Bottom-right: strong red/orange
            br_x = np.clip(1.0 - X.astype(np.float32) / (w * 0.6), 0, 1)
            br_y = np.clip(1.0 - Y.astype(np.float32) / (h * 0.6), 0, 1)
            br_mask = (br_x * br_y) ** 1.3
            r += br_mask * 150 * warmth
            g += br_mask * 30 * warmth
            b -= br_mask * 40 * warmth

            # Top-left: pinkish/red
            tl_x = np.clip(X.astype(np.float32) / (w * 0.6), 0, 1)
            tl_y = np.clip(Y.astype(np.float32) / (h * 0.6), 0, 1)
            tl_mask = (tl_x * tl_y) ** 1.6
            r += tl_mask * 100 * warmth
            g -= tl_mask * 10 * warmth
            b += tl_mask * 20 * warmth

            # Bottom-left: warm yellow/green
            bl_x = np.clip(X.astype(np.float32) / (w * 0.7), 0, 1)
            bl_y = np.clip(1.0 - Y.astype(np.float32) / (h * 0.7), 0, 1)
            bl_mask = (bl_x * bl_y) ** 1.5
            r += bl_mask * 80 * warmth
            g += bl_mask * 60 * warmth
            b -= bl_mask * 30 * warmth

            # ── Dark vignette (darkens corners) ──
            cx, cy = w / 2.0, h / 2.0
            max_dist = np.sqrt(cx**2 + cy**2)
            dist = np.sqrt((X - cx)**2 + (Y - cy)**2) / max_dist
            vignette_mask = np.clip(dist ** 1.2, 0, 1)
            r -= vignette_mask * 50 * warmth
            g -= vignette_mask * 50 * warmth
            b -= vignette_mask * 45 * warmth

            # ── Very slight warm wash (preserve original colors) ──
            r += 8 * warmth
            g += 3 * warmth
            b -= 8 * warmth

            f[:,:,0] = r
            f[:,:,1] = g
            f[:,:,2] = b
            f = np.clip(f, 0, 255)

            # Convert to uint8 for reliable cv2 drawing, then back
            f_u8 = np.clip(f, 0, 255).astype(np.uint8)

            # Seed changes ~every 10 frames (at 30fps, 10 frames ≈ 0.33s)
            frame_seed = int(time.time() * 3) % (2**31)
            rng = np.random.RandomState(frame_seed)

            # ── Single straight vertical scratch (dark at top, fading to light at bottom) ──
            cx_pos = int(rng.randint(int(w * 0.1), int(w * 0.9)))
            brightness_top = int(rng.choice([140, 160, 180]))
            overlay = f_u8.copy()
            cv2.line(overlay, (cx_pos, 0), (cx_pos, h),
                     (brightness_top, brightness_top, brightness_top), 1, cv2.LINE_AA)
            # Gradient mask: 1.0 at top -> 0.0 at bottom
            grad = np.linspace(1.0, 0.0, h).astype(np.float32).reshape(h, 1)
            grad_mask3 = np.stack([grad] * 3, axis=-1)
            alpha_base = rng.uniform(0.45, 0.7)
            f_u8 = (overlay.astype(np.float32) * grad_mask3 * alpha_base +
                    f_u8.astype(np.float32) * (1.0 - grad_mask3 * alpha_base))
            f_u8 = np.clip(f_u8, 0, 255).astype(np.uint8)

            # ── Small C-shaped and crooked scratches (lightly visible) ──
            num_small = rng.randint(2, 5)
            for _ in range(num_small):
                sx = int(rng.randint(0, w))
                sy = int(rng.randint(0, h))
                scr_len = rng.randint(15, 50)
                brightness_s = int(rng.choice([170, 190, 210, 230]))
                if rng.randint(0, 2) == 0:
                    num_arc = rng.randint(3, 6)
                    radius = rng.randint(8, scr_len)
                    start_angle = rng.uniform(0, 2 * np.pi)
                    arc_span = rng.uniform(np.pi * 0.5, np.pi * 1.5)
                    pts = []
                    for a in range(num_arc):
                        angle = start_angle + (a / (num_arc - 1)) * arc_span
                        px = int(np.clip(sx + radius * np.cos(angle), 0, w - 1))
                        py = int(np.clip(sy + radius * np.sin(angle), 0, h - 1))
                        pts.append([px, py])
                    pts_arr = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
                else:
                    num_seg = rng.randint(2, 5)
                    pts = [[sx, sy]]
                    for _ in range(num_seg - 1):
                        angle = rng.uniform(0, 2 * np.pi)
                        seg_len = rng.randint(5, 20)
                        nx = int(np.clip(pts[-1][0] + seg_len * np.cos(angle), 0, w - 1))
                        ny = int(np.clip(pts[-1][1] + seg_len * np.sin(angle), 0, h - 1))
                        pts.append([nx, ny])
                    pts_arr = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
                overlay2 = f_u8.copy()
                cv2.polylines(overlay2, [pts_arr], False,
                              (brightness_s, brightness_s, brightness_s), 1, cv2.LINE_AA)
                alpha_s = rng.uniform(0.3, 0.5)
                f_u8 = cv2.addWeighted(overlay2, alpha_s, f_u8, 1.0 - alpha_s, 0)

            # ── Film grain (subtle) ──
            grain = rng.normal(0, 6, f_u8.shape).astype(np.int16)
            f_out = f_u8.astype(np.int16) + grain
            f = np.clip(f_out, 0, 255).astype(np.float32)
            # Sync r,g,b so the post-style block doesn't overwrite scratches
            r = f[:,:,0].copy()
            g = f[:,:,1].copy()
            b = f[:,:,2].copy()

        elif style == "BW Memories":
            # Convert to grayscale
            gray = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32)
            # Slight contrast boost
            gray = (gray - 128) * 1.15 + 128
            # Lift blacks slightly for faded film look
            gray = gray * 0.9 + 25
            r = gray.copy()
            g = gray.copy()
            b = gray.copy()
            f[:,:,0] = r
            f[:,:,1] = g
            f[:,:,2] = b
            f = np.clip(f, 0, 255)

            f_u8 = np.clip(f, 0, 255).astype(np.uint8)

            # Grain changes every frame
            grain_seed = int(time.time() * 1000000) % (2**31)
            rng_grain = np.random.RandomState(grain_seed)
            grain = rng_grain.normal(0, 10, f_u8.shape).astype(np.int16)
            f_u8 = np.clip(f_u8.astype(np.int16) + grain, 0, 255).astype(np.uint8)

            # Scratches + black dots change every 3 frames (~0.1s at 30fps)
            scratch_seed = int(time.time() * 10) % (2**31)
            rng = np.random.RandomState(scratch_seed)

            # ── Single straight vertical scratch (dark top, fading bottom) ──
            cx_pos = int(rng.randint(int(w * 0.1), int(w * 0.9)))
            brightness_top = int(rng.choice([180, 200, 220]))
            overlay = f_u8.copy()
            cv2.line(overlay, (cx_pos, 0), (cx_pos, h),
                     (brightness_top, brightness_top, brightness_top), 1, cv2.LINE_AA)
            grad = np.linspace(1.0, 0.0, h).astype(np.float32).reshape(h, 1)
            grad_mask3 = np.stack([grad] * 3, axis=-1)
            alpha_base = rng.uniform(0.4, 0.65)
            f_u8 = (overlay.astype(np.float32) * grad_mask3 * alpha_base +
                    f_u8.astype(np.float32) * (1.0 - grad_mask3 * alpha_base))
            f_u8 = np.clip(f_u8, 0, 255).astype(np.uint8)

            # ── Small C-shaped and crooked scratches (2-3) ──
            num_small = rng.randint(2, 4)
            for _ in range(num_small):
                sx = int(rng.randint(0, w))
                sy = int(rng.randint(0, h))
                scr_len = rng.randint(15, 50)
                brightness_s = int(rng.choice([170, 190, 210]))
                if rng.randint(0, 2) == 0:
                    num_arc = rng.randint(3, 6)
                    radius = rng.randint(8, scr_len)
                    start_angle = rng.uniform(0, 2 * np.pi)
                    arc_span = rng.uniform(np.pi * 0.5, np.pi * 1.5)
                    pts = []
                    for a in range(num_arc):
                        angle = start_angle + (a / (num_arc - 1)) * arc_span
                        px = int(np.clip(sx + radius * np.cos(angle), 0, w - 1))
                        py = int(np.clip(sy + radius * np.sin(angle), 0, h - 1))
                        pts.append([px, py])
                    pts_arr = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
                else:
                    num_seg = rng.randint(2, 5)
                    pts = [[sx, sy]]
                    for _ in range(num_seg - 1):
                        angle = rng.uniform(0, 2 * np.pi)
                        seg_len = rng.randint(5, 20)
                        nx = int(np.clip(pts[-1][0] + seg_len * np.cos(angle), 0, w - 1))
                        ny = int(np.clip(pts[-1][1] + seg_len * np.sin(angle), 0, h - 1))
                        pts.append([nx, ny])
                    pts_arr = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
                overlay2 = f_u8.copy()
                cv2.polylines(overlay2, [pts_arr], False,
                              (brightness_s, brightness_s, brightness_s), 1, cv2.LINE_AA)
                alpha_s = rng.uniform(0.3, 0.5)
                f_u8 = cv2.addWeighted(overlay2, alpha_s, f_u8, 1.0 - alpha_s, 0)

            # ── Black dust spots (grain-sized, change every 3 frames) ──
            num_dots = rng.randint(12, 25)
            for _ in range(num_dots):
                dx = int(rng.randint(0, w))
                dy = int(rng.randint(0, h))
                dc = int(rng.randint(10, 60))
                overlay3 = f_u8.copy()
                cv2.circle(overlay3, (dx, dy), 1, (dc, dc, dc), -1, cv2.LINE_AA)
                alpha_d = rng.uniform(0.25, 0.5)
                f_u8 = cv2.addWeighted(overlay3, alpha_d, f_u8, 1.0 - alpha_d, 0)

            f = f_u8.astype(np.float32)
            r = f[:,:,0].copy()
            g = f[:,:,1].copy()
            b = f[:,:,2].copy()

        elif style == "Teal & Orange":
            shadow_mask = np.clip(1.0 - lum / 100.0, 0, 1)
            highlight_mask = np.clip((lum - 155) / 100.0, 0, 1)
            # Teal shadows
            b += shadow_mask * 25 * warmth
            g += shadow_mask * 10 * warmth
            r -= shadow_mask * 10 * warmth
            # Orange highlights
            r += highlight_mask * 35 * warmth
            g += highlight_mask * 10 * warmth
            b -= highlight_mask * 25 * warmth

        elif style == "Bleach Bypass":
            gray = lum
            r = r * 0.5 + gray * 0.5
            g = g * 0.5 + gray * 0.5
            b = b * 0.5 + gray * 0.5
            # Increase contrast
            r = (r - 128) * 1.4 + 128
            g = (g - 128) * 1.4 + 128
            b = (b - 128) * 1.4 + 128

        elif style == "Cold Blue":
            r -= 15 * warmth
            g -= 5 * warmth
            b += 30 * warmth

        elif style == "Desaturated":
            r = r * 0.6 + lum * 0.4
            g = g * 0.6 + lum * 0.4
            b = b * 0.6 + lum * 0.4
            r += 5 * warmth
            b -= 5 * warmth

        elif style == "High Contrast":
            r = (r - 128) * 1.5 + 128
            g = (g - 128) * 1.5 + 128
            b = (b - 128) * 1.5 + 128
            r += 10 * warmth
            b -= 10 * warmth

        # Apply saturation
        if saturation != 1.0:
            gray = lum
            r = r * saturation + gray * (1 - saturation)
            g = g * saturation + gray * (1 - saturation)
            b = b * saturation + gray * (1 - saturation)

        # Fade blacks (lift shadows)
        if fade_blacks > 0:
            lift = fade_blacks * 255
            shadow_mask = np.clip(1.0 - lum / 128.0, 0, 1)
            r += shadow_mask * lift
            g += shadow_mask * lift * 0.9
            b += shadow_mask * lift * 0.8

        f[:,:,0] = r
        f[:,:,1] = g
        f[:,:,2] = b
        f = np.clip(f, 0, 255)

        # Blend with original based on intensity
        result = frame.astype(np.float32) * (1 - intensity) + f * intensity
        return np.clip(result, 0, 255).astype(np.uint8)
