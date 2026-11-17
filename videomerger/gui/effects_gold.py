"""God-ray, aura and gold-outline effect rendering.

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


class EffectsGoldMixin:
    """God-ray, aura and gold-outline effect rendering."""

    def _create_god_ray_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, drawn_edges=None):
        h, w = frame.shape[:2]
        base = original_mask if original_mask is not None else mask
        # Compute edges from the original mask to preserve fine details (fingers, gaps)
        base_u8 = (np.clip(base, 0, 1) * 255).astype(np.uint8)
        edges = cv2.Canny(base_u8, 20, 80)
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
        edge_mask = cv2.GaussianBlur(edges, (5, 5), 0).astype(np.float32) / 255.0
        outer_edge = cv2.dilate(edges, np.ones((7, 7), np.uint8), iterations=1)
        outer_edge = cv2.GaussianBlur(outer_edge, (11, 11), 0).astype(np.float32) / 255.0
        # Thick ring from lightly smoothed base (preserves finger contours)
        base_smooth = cv2.GaussianBlur(base, (5, 5), 0)
        base_smooth_u8 = (np.clip(base_smooth, 0, 1) * 255).astype(np.uint8)
        thick_ring = cv2.dilate(base_smooth_u8, np.ones((7, 7), np.uint8), iterations=2)
        thick_ring_inner = cv2.erode(base_smooth_u8, np.ones((3, 3), np.uint8), iterations=1)
        thick_ring = np.clip(thick_ring.astype(np.float32) - thick_ring_inner.astype(np.float32), 0, 255) / 255.0
        thick_ring = cv2.GaussianBlur(thick_ring, (5, 5), 0)
        # Erode base to open narrow gaps (e.g., between fingers) so light passes through
        base_eroded = cv2.erode(base_u8, np.ones((3, 3), np.uint8), iterations=1)
        inv_mask = 1.0 - base_eroded.astype(np.float32) / 255.0
        inv_mask = cv2.GaussianBlur(inv_mask, (7, 7), 0)
        # Incorporate drawn edges with same styling as regular edge_mask
        if drawn_edges is not None and drawn_edges.max() > 0:
            de = cv2.GaussianBlur(drawn_edges, (5, 5), 0).astype(np.float32)
            edge_mask = np.maximum(edge_mask, de)
            de_outer = cv2.dilate((drawn_edges * 255).astype(np.uint8), np.ones((7, 7), np.uint8), iterations=1)
            de_outer = cv2.GaussianBlur(de_outer, (11, 11), 0).astype(np.float32) / 255.0
            outer_edge = np.maximum(outer_edge, de_outer)
        # Bright inner edge glow (inner color)
        edge_layer = np.zeros_like(frame, dtype=np.float32)
        edge_layer[:] = color_inner
        edge_layer *= edge_mask[..., np.newaxis] * glow * time_factor * 3.0
        # Thick outline ring (inner color)
        ring_layer = np.zeros_like(frame, dtype=np.float32)
        ring_layer[:] = color_inner
        ring_layer *= thick_ring[..., np.newaxis] * glow * time_factor * 2.5
        # Soft outer glow (outer color)
        glow_layer = np.zeros_like(frame, dtype=np.float32)
        glow_layer[:] = color_outer
        glow_layer *= outer_edge[..., np.newaxis] * glow * time_factor * 2.0
        glow_layer = cv2.GaussianBlur(glow_layer, (15, 15), 0)
        glow_layer *= inv_mask[..., np.newaxis]
        edge_layer *= inv_mask[..., np.newaxis]
        ring_layer *= inv_mask[..., np.newaxis]
        combined = frame.astype(np.float32)
        combined += glow_layer * opacity
        combined += edge_layer * opacity
        combined += ring_layer * opacity
        dark_mask = np.exp(-((np.arange(h)[:, None] - h*0.5)**2 + (np.arange(w)[None, :] - w*0.5)**2) / (2 * (max(h,w)*0.6)**2))
        crush = 1.0 - (1.0 - dark_mask[..., np.newaxis]) * 0.3 * opacity * time_factor
        combined *= crush
        return np.clip(combined, 0, 255).astype(np.uint8)

    def _create_ethereal_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, drawn_edges=None):
        h, w = frame.shape[:2]
        base = original_mask if original_mask is not None else mask
        # Compute edges from the original mask to preserve fine details (fingers, gaps)
        base_u8 = (np.clip(base, 0, 1) * 255).astype(np.uint8)
        edges = cv2.Canny(base_u8, 20, 80)
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
        edge_mask = cv2.GaussianBlur(edges, (7, 7), 0).astype(np.float32) / 255.0
        outer_edge = cv2.dilate(edges, np.ones((9, 9), np.uint8), iterations=1)
        outer_edge = cv2.GaussianBlur(outer_edge, (17, 17), 0).astype(np.float32) / 255.0
        # Thick ring from lightly smoothed base (preserves finger contours)
        base_smooth = cv2.GaussianBlur(base, (5, 5), 0)
        base_smooth_u8 = (np.clip(base_smooth, 0, 1) * 255).astype(np.uint8)
        thick_ring = cv2.dilate(base_smooth_u8, np.ones((9, 9), np.uint8), iterations=2)
        thick_ring_inner = cv2.erode(base_smooth_u8, np.ones((3, 3), np.uint8), iterations=1)
        thick_ring = np.clip(thick_ring.astype(np.float32) - thick_ring_inner.astype(np.float32), 0, 255) / 255.0
        thick_ring = cv2.GaussianBlur(thick_ring, (7, 7), 0)
        # Erode base to open narrow gaps (e.g., between fingers) so light passes through
        base_eroded = cv2.erode(base_u8, np.ones((3, 3), np.uint8), iterations=1)
        inv_mask = 1.0 - base_eroded.astype(np.float32) / 255.0
        inv_mask = cv2.GaussianBlur(inv_mask, (7, 7), 0)
        # Incorporate drawn edges with same styling as regular edge_mask
        if drawn_edges is not None and drawn_edges.max() > 0:
            de = cv2.GaussianBlur(drawn_edges, (7, 7), 0).astype(np.float32)
            edge_mask = np.maximum(edge_mask, de)
            de_outer = cv2.dilate((drawn_edges * 255).astype(np.uint8), np.ones((9, 9), np.uint8), iterations=1)
            de_outer = cv2.GaussianBlur(de_outer, (17, 17), 0).astype(np.float32) / 255.0
            outer_edge = np.maximum(outer_edge, de_outer)
        # Bright inner edge (inner color)
        edge_layer = np.zeros_like(frame, dtype=np.float32)
        edge_layer[:] = color_inner
        edge_layer *= edge_mask[..., np.newaxis] * glow * time_factor * 3.5
        # Thick outline ring (inner color)
        ring_layer = np.zeros_like(frame, dtype=np.float32)
        ring_layer[:] = color_inner
        ring_layer *= thick_ring[..., np.newaxis] * glow * time_factor * 3.0
        # Soft outer glow (outer color)
        glow_layer = np.zeros_like(frame, dtype=np.float32)
        glow_layer[:] = color_outer
        glow_layer *= outer_edge[..., np.newaxis] * glow * time_factor * 2.5
        glow_layer = cv2.GaussianBlur(glow_layer, (21, 21), 0)
        glow_layer *= inv_mask[..., np.newaxis]
        edge_layer *= inv_mask[..., np.newaxis]
        ring_layer *= inv_mask[..., np.newaxis]
        combined = frame.astype(np.float32)
        combined += glow_layer * opacity
        combined += edge_layer * opacity
        combined += ring_layer * opacity
        dark_mask = np.exp(-((np.arange(h)[:, None] - h*0.5)**2 + (np.arange(w)[None, :] - w*0.5)**2) / (2 * (max(h,w)*0.5)**2))
        crush = 1.0 - (1.0 - dark_mask[..., np.newaxis]) * 0.4 * opacity * time_factor
        combined *= crush
        return np.clip(combined, 0, 255).astype(np.uint8)

    def _create_divine_effect(self, frame, mask, ray_color, opacity, glow, time_factor, original_mask=None, drawn_edges=None):
        h, w = frame.shape[:2]
        base = original_mask if original_mask is not None else mask

        # Distance-based edge detection on original mask (preserves finger gaps)
        base_uint8 = (np.clip(base, 0, 1) * 255).astype(np.uint8)
        dist = cv2.distanceTransform(base_uint8, cv2.DIST_L2, 5)
        dist_norm = np.clip(dist / max(dist.max(), 1), 0, 1).astype(np.float32)

        # Thin edge from distance gradient (peak at the boundary)
        edge_inner = np.clip(dist_norm - 0.5, 0, 0.5) * 2.0
        edge_outer = np.clip(0.5 - dist_norm, 0, 0.5) * 2.0
        thin_edge = np.clip(edge_inner + edge_outer, 0, 1)

        # Thicker ring from smoothed mask (for smooth glow contours)
        smooth_mask = self._smooth_mask_for_outline(mask)
        smooth_uint8 = (smooth_mask * 255).astype(np.uint8)
        dilate_k = np.ones((11, 11), np.uint8)
        erode_k = np.ones((5, 5), np.uint8)
        dilated = cv2.dilate(smooth_uint8, dilate_k, iterations=1)
        eroded = cv2.erode(smooth_uint8, erode_k, iterations=1)
        thick_ring = np.clip(dilated.astype(np.float32) - eroded.astype(np.float32), 0, 255) / 255.0
        thick_ring = cv2.GaussianBlur(thick_ring, (9, 9), 0)

        # Soft outer glow from distance field of original mask
        outer_glow = np.clip(1.0 - dist_norm, 0, 1)
        outer_glow = cv2.GaussianBlur(outer_glow, (21, 21), 0)

        base_eroded = cv2.erode(base_uint8, np.ones((3, 3), np.uint8), iterations=1)
        inv_mask = 1.0 - cv2.GaussianBlur(base_eroded.astype(np.float32) / 255.0, (7, 7), 0)

        combined = frame.astype(np.float32)

        # Thin bright edge
        edge_layer = np.zeros_like(frame, dtype=np.float32)
        edge_layer[:] = ray_color
        edge_layer *= thin_edge[..., np.newaxis] * glow * time_factor * 4.0

        # Thick gold ring
        ring_layer = np.zeros_like(frame, dtype=np.float32)
        ring_layer[:] = ray_color
        ring_layer *= thick_ring[..., np.newaxis] * glow * time_factor * 3.5

        # Soft outer glow
        glow_layer = np.zeros_like(frame, dtype=np.float32)
        glow_layer[:] = ray_color
        glow_layer *= outer_glow[..., np.newaxis] * glow * time_factor * 2.5

        edge_layer *= inv_mask[..., np.newaxis]
        ring_layer *= inv_mask[..., np.newaxis]
        glow_layer *= inv_mask[..., np.newaxis]

        combined += edge_layer * opacity
        combined += ring_layer * opacity
        combined += glow_layer * opacity
        return np.clip(combined, 0, 255).astype(np.uint8)

    def _create_brilliance_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, drawn_edges=None):
        h, w = frame.shape[:2]
        base = original_mask if original_mask is not None else mask

        # Convert RGB to BGR for OpenCV (inner = core, outer = halo/wrap)
        GOLD_BGR = np.array([color_inner[2], color_inner[1], color_inner[0]], dtype=np.float32)
        OUTER_BGR = np.array([color_outer[2], color_outer[1], color_outer[0]], dtype=np.float32)

        # ════════════════════════════════════════════════════════════════
        # STEP 1: MASK PRE-PROCESSING — Clean the Emitter
        # ════════════════════════════════════════════════════════════════
        base_uint8 = (np.clip(base, 0, 1) * 255).astype(np.uint8)
        _, binary = cv2.threshold(base_uint8, 30, 255, cv2.THRESH_BINARY)
        kernel_clean = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_clean)
        clean_mask_u8 = binary

        soft_mask = cv2.GaussianBlur(binary, (11, 11), 0)
        mask_f32 = soft_mask.astype(np.float32) / 255.0
        mask_3ch = cv2.merge([mask_f32, mask_f32, mask_f32])

        # ════════════════════════════════════════════════════════════════
        # STEP 2: EMISSIVE LIGHT SOURCE — golden on black canvas
        # ════════════════════════════════════════════════════════════════
        gold_emissive = np.zeros((h, w, 3), dtype=np.float32)
        gold_emissive[:, :] = GOLD_BGR / 255.0
        light_source = gold_emissive * mask_3ch

        # ════════════════════════════════════════════════════════════════
        # STEP 3: FIND ORIGIN — upper chest/head area
        # ════════════════════════════════════════════════════════════════
        ys, xs = np.where(clean_mask_u8 > 0)
        if len(xs) > 0:
            center = (
                int(np.mean(xs)),
                int(np.min(ys) + (np.max(ys) - np.min(ys)) * 0.25)
            )
        else:
            center = (w // 2, h // 3)

        # ════════════════════════════════════════════════════════════════
        # STEP 4: VOLUMETRIC ACCUMULATION LOOP (The God Rays)
        # ════════════════════════════════════════════════════════════════
        ray_buffer = np.zeros_like(light_source)
        N = 100
        wgt = 0.05
        decay = 0.96

        for i in range(N):
            scale = 1.0 + i * 0.004
            M = cv2.getRotationMatrix2D(center, 0.0, scale)
            warped = cv2.warpAffine(
                light_source, M, (w, h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0)
            )
            ray_buffer += warped * wgt
            wgt *= decay

        # ════════════════════════════════════════════════════════════════
        # STEP 5: CORE HALO & OVEREXPOSURE (HDR Bloom Simulation)
        # ════════════════════════════════════════════════════════════════
        halo = cv2.GaussianBlur(mask_3ch, (81, 81), 0)
        gold_halo = halo * (OUTER_BGR / 255.0)
        white_core = np.clip((halo ** 3) * 1.5, 0.0, 1.0)

        total_light = ray_buffer + gold_halo + white_core
        total_light_u8 = np.clip(total_light * 255.0, 0, 255).astype(np.uint8)
        total_light_u8 = cv2.GaussianBlur(total_light_u8, (15, 15), 0)

        eff = float(opacity * glow * time_factor)
        total_light_u8 = cv2.convertScaleAbs(total_light_u8, alpha=eff)

        # ════════════════════════════════════════════════════════════════
        # STEP 6: FINAL COMPOSITING STACK
        # ════════════════════════════════════════════════════════════════
        bg_darkened = cv2.convertScaleAbs(frame, alpha=0.5, beta=0)
        glowing_bg = cv2.add(bg_darkened, total_light_u8)

        subject = cv2.bitwise_and(frame, frame, mask=clean_mask_u8)
        inv_mask = cv2.bitwise_not(clean_mask_u8)
        final_bg = cv2.bitwise_and(glowing_bg, glowing_bg, mask=inv_mask)
        output = cv2.add(final_bg, subject)

        # ════════════════════════════════════════════════════════════════
        # STEP 7: LIGHT WRAP — bleed light over subject's edges
        # ════════════════════════════════════════════════════════════════
        wrap_mask = cv2.GaussianBlur(clean_mask_u8, (11, 11), 0)
        edge_spill = cv2.bitwise_and(wrap_mask, inv_mask)
        edge_f = edge_spill.astype(np.float32) / 255.0
        light_wrap = cv2.merge([
            (edge_f * OUTER_BGR[0]).astype(np.uint8),
            (edge_f * OUTER_BGR[1]).astype(np.uint8),
            (edge_f * OUTER_BGR[2]).astype(np.uint8),
        ])
        final_frame = cv2.add(output, light_wrap)

        if drawn_edges is not None and drawn_edges.max() > 0:
            de = cv2.GaussianBlur(drawn_edges, (5, 5), 0).astype(np.float32)
            de_layer = np.zeros((h, w, 3), dtype=np.float32)
            de_layer[:] = GOLD_BGR / 255.0
            de_layer *= de[..., np.newaxis] * glow * time_factor * 3.0
            de_layer = np.clip(de_layer * 255, 0, 255).astype(np.uint8)
            final_frame = cv2.add(final_frame, de_layer)

        return final_frame

    def _create_kaka_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, drawn_edges=None):
        h, w = frame.shape[:2]
        frame_f = frame.astype(np.float32)
        mask = self._smooth_mask_for_outline(mask)
        base = original_mask if original_mask is not None else mask
        base = np.clip(base, 0, 1)
        GOLD_INNER = np.array(color_inner, dtype=np.float32)
        GOLD_OUTER = np.array(color_outer, dtype=np.float32)
        diag = float(np.sqrt(w * w + h * h))

        # --- 1. MASK EXTRACTION ---
        subj = base.copy()

        # --- 2. BASE AURA (Glow) ---
        # Gaussian blur on the mask, tinted golden yellow #FFC832
        aura = cv2.GaussianBlur(subj, (31, 31), 0)
        aura = cv2.GaussianBlur(aura, (0, 0), sigmaX=15.0)
        aura = np.clip(aura, 0, 1)
        base_aura = aura[..., np.newaxis] * GOLD_INNER * glow * time_factor * 2.5

        # --- 3. GOD RAYS (Volumetric Light Scattering / Zoom Blur) ---
        # Center point = center of the subject
        ys, xs = np.where(subj > 0.3)
        if len(xs) > 0 and len(ys) > 0:
            cy, cx = int(np.mean(ys)), int(np.mean(xs))
        else:
            cy, cx = h // 2, w // 2

        Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
        dy = Y - cy
        dx = X - cx

        # Accumulation loop: Color_rays = sum_{i=0}^{N} Texture(UV_scaled_i) * Weight * Decay^i
        N = 64
        decay = 0.92
        weight = 0.08
        scale_step = 0.025
        accumulator = np.zeros((h, w), dtype=np.float32)

        for i in range(N):
            scale = 1.0 + i * scale_step
            # Map each pixel back to the source position under this zoom scale
            src_y = cy + dy / scale
            src_x = cx + dx / scale
            # Clamp to valid range
            src_y = np.clip(src_y, 0, h - 1)
            src_x = np.clip(src_x, 0, w - 1)
            # Sample the mask at the scaled position (bilinear would be better but nearest is fine for mask)
            sy_f = np.floor(src_y).astype(np.int32)
            sx_f = np.floor(src_x).astype(np.int32)
            sy_f = np.clip(sy_f, 0, h - 1)
            sx_f = np.clip(sx_f, 0, w - 1)
            sample = subj[sy_f, sx_f]
            accumulator += sample * weight * (decay ** i)

        # Normalize and soften the ray accumulation
        god_rays = np.clip(accumulator, 0, 1)
        god_rays = cv2.GaussianBlur(god_rays, (5, 5), 0)
        rays_colored = god_rays[..., np.newaxis] * GOLD_OUTER * glow * time_factor * 4.0

        # --- 5. BACKGROUND PROCESSING ---
        bg = frame_f.copy()
        bg_lum = bg[..., 0] * 0.299 + bg[..., 1] * 0.587 + bg[..., 2] * 0.114
        bg_mean = bg_lum.mean()
        contrast_factor = 0.70
        for c in range(3):
            bg[..., c] = bg_mean + (bg[..., c] - bg_mean) * contrast_factor
        bg *= 0.65
        bg = np.clip(bg, 0, 255)

        # --- 6. ADDITIVE BLENDING ---
        # C_final = C_bg + C_glow  (strict additive, no alpha blending)
        glow_all = base_aura + rays_colored
        result = bg + glow_all * opacity
        result = np.clip(result, 0, 255)

        # --- 7. FINAL COMPOSITE ---
        subj_3ch = subj[..., np.newaxis]
        result = result * (1.0 - subj_3ch) + frame_f * subj_3ch
        result = np.clip(result, 0, 255)

        if drawn_edges is not None and drawn_edges.max() > 0:
            de = cv2.GaussianBlur(drawn_edges, (5, 5), 0).astype(np.float32)
            result_f = result.astype(np.float32)
            result_f += de[..., np.newaxis] * GOLD_INNER * glow * time_factor * 3.0
            result = np.clip(result_f, 0, 255)

        return result.astype(np.uint8)

    def _find_head_position(self, frame, mask_bool, cy, cx, bbox=None):
        h, w = frame.shape[:2]

        # Priority 1: Face detection via Haar cascade (handles tilted heads well)
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            face_cascade = cv2.CascadeClassifier(
                _HAAR_CASCADE_PATH)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
            if len(faces) > 0:
                largest = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = largest
                return (fy + fh // 2, fx + fw // 2)
        except Exception:
            pass

        # Priority 2: YOLO bounding box — use top-center of the bbox
        if bbox is not None:
            bx, by, bw, bh = bbox
            head_cx = bx + bw // 2
            head_cy = by + max(5, int(bh * 0.12))
            return (head_cy, head_cx)

        # Priority 3: Mask-based head detection — find head by scanning top of mask
        ys, xs = np.where(mask_bool)
        if len(ys) < 10:
            return (cy, cx)

        y_min, y_max = int(ys.min()), int(ys.max())
        person_height = y_max - y_min
        if person_height < 30:
            return (cy, cx)

        # Scan only the top 30% of the person (head + shoulders region)
        scan_limit = y_min + int(person_height * 0.30)
        last_span = None
        neck_row = y_min

        for row_y in range(y_min, min(scan_limit, y_max)):
            row_pixels = xs[ys == row_y]
            if len(row_pixels) < 5:
                continue
            span = row_pixels.max() - row_pixels.min()
            if last_span is not None and span > last_span * 1.6 and span > 40:
                neck_row = row_y
                break
            last_span = span

        # If no clear widening found, use the top region centroid
        if neck_row == y_min:
            neck_row = y_min + int(scan_limit - y_min) // 3

        head_cy = (y_min + neck_row) // 2

        # Head center X: median of mask pixels in the head band (more robust than mean)
        head_band = (ys >= y_min) & (ys <= neck_row)
        hxs = xs[head_band]
        head_cx = int(np.median(hxs)) if len(hxs) > 10 else cx

        return (head_cy, head_cx)

    def _create_holy_aura_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, bbox=None, drawn_edges=None):
        h, w = frame.shape[:2]
        mask = self._smooth_mask_for_outline(mask)
        base = original_mask if original_mask is not None else mask
        mask_bool = base > 0.3

        ys, xs = np.where(mask_bool)
        if len(xs) > 0 and len(ys) > 0:
            cy = int(np.mean(ys))
            cx = int(np.mean(xs))
        else:
            cy, cx = h // 2, w // 2

        inv_uint8 = (np.clip(1.0 - base, 0, 1) * 255).astype(np.uint8)
        dist_outside = cv2.distanceTransform(inv_uint8, cv2.DIST_L2, 5).astype(np.float32)

        head_cy, head_cx = self._find_head_position(frame, mask_bool, cy, cx, bbox)

        Y, X = np.mgrid[:h, :w]
        head_dx = (X - head_cx).astype(np.float32)
        head_dy = (Y - head_cy).astype(np.float32)
        head_dist = np.sqrt(head_dx**2 + head_dy**2)
        head_angle = np.arctan2(head_dy, head_dx)
        diag = np.sqrt(w * w + h * h)

        outside_mask = 1.0 - cv2.GaussianBlur(base, (5, 5), 0)
        inside_mask = cv2.GaussianBlur(base, (5, 5), 0)

        golden_layer = np.zeros_like(frame, dtype=np.float32)

        color_inner_f = np.array(color_inner, dtype=np.float32)
        color_outer_f = np.array(color_outer, dtype=np.float32)

        # 1. Center bloom behind head (inner color — vibrant core)
        bloom_r = diag * 0.06
        bloom = np.clip(1.0 - head_dist / bloom_r, 0, 1) ** 0.8
        bloom *= outside_mask
        golden_layer += bloom[..., np.newaxis] * color_inner_f * glow * time_factor * 8.0

        # 2. Warm glow expanding outward (outer color — aura)
        glow_r = diag * 0.12
        warm_glow = np.clip(1.0 - head_dist / glow_r, 0, 1) ** 1.5
        warm_glow *= outside_mask
        golden_layer += warm_glow[..., np.newaxis] * color_outer_f * glow * time_factor * 4.0

        # 3. Wide soft rays (outer color — light beams)
        num_rays = 16
        ray_mask = np.zeros((h, w), dtype=np.float32)
        for i in range(num_rays):
            ray_angle = (2.0 * np.pi * i) / num_rays
            angular_diff = np.abs(np.arctan2(np.sin(head_angle - ray_angle), np.cos(head_angle - ray_angle)))
            ray_cone = np.clip(1.0 - angular_diff / 0.12, 0, 1) ** 2.0
            ray_mask += ray_cone
        ray_mask = np.clip(ray_mask, 0, 1)
        ray_mask *= np.clip(1.0 - (head_dist / (diag * 0.50)) ** 0.5, 0, 1)
        ray_mask *= outside_mask
        ray_mask = cv2.GaussianBlur(ray_mask, (11, 11), 0)
        golden_layer += ray_mask[..., np.newaxis] * color_outer_f * glow * time_factor * 3.0

        # 4. Outer atmospheric haze (outer color)
        haze_r = diag * 0.22
        haze = np.clip(1.0 - head_dist / haze_r, 0, 1) ** 2.0
        haze *= outside_mask
        haze = cv2.GaussianBlur(haze, (25, 25), 0)
        golden_layer += haze[..., np.newaxis] * color_outer_f * glow * time_factor * 1.2

        # 5. Soft outline around person body (inner color — sharp edge)
        edge_width = 8.0
        edge_out = np.clip(dist_outside / edge_width, 0, 1)
        edge_out = 1.0 - edge_out
        edge_out = np.clip(edge_out, 0, 1)
        edge_out = cv2.GaussianBlur(edge_out, (5, 5), 0)
        golden_layer += edge_out[..., np.newaxis] * color_inner_f * glow * time_factor * 4.0

        # COMPOSITE
        combined = frame.astype(np.float32)

        # Gentle background darkening — keep background visible
        bg_darken = np.clip(dist_outside / (diag * 0.40), 0, 1) ** 1.5
        bg_darken = 0.45 + 0.55 * bg_darken
        bg_factor = inside_mask * 1.0 + (1.0 - inside_mask) * bg_darken
        combined *= bg_factor[..., np.newaxis]

        # Add golden light to background only
        combined += golden_layer * opacity * outside_mask[..., np.newaxis]

        if drawn_edges is not None and drawn_edges.max() > 0:
            de = cv2.GaussianBlur(drawn_edges, (5, 5), 0).astype(np.float32)
            combined += de[..., np.newaxis] * color_inner_f * glow * time_factor * 3.0

        return np.clip(combined, 0, 255).astype(np.uint8)

    def apply_dreamy_angel_effect(self, frame, item, t):
        if item.get('effect', 'none') != 'gold_outline':
            return frame
        if not self.effect_global_enabled.get():
            return frame

        opacity = float(item.get('effect_opacity', 0.7))
        glow = float(item.get('effect_glow', 0.7))
        variation = item.get('effect_variation', 'ethereal')
        if opacity <= 0 and glow <= 0:
            return frame

        timing = item.get('effect_timing', 'full_clip')
        eff_start = float(item.get('effect_start', 0.0))
        eff_end = float(item.get('effect_end', 5.0))

        if timing == 'custom':
            if t < eff_start or t > eff_end:
                return frame
            eff_dur = eff_end - eff_start
            local_t = t - eff_start
            fade_in = eff_dur * 0.20
            fade_out = eff_dur * 0.20
            if local_t < fade_in:
                time_factor = local_t / fade_in if fade_in > 0 else 0.0
            elif local_t > (eff_dur - fade_out):
                remain = eff_dur - local_t
                time_factor = remain / fade_out if fade_out > 0 else 0.0
            else:
                time_factor = 1.0
        else:
            time_factor = 1.0

        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame

        # Use person-specific mask when a person is selected,
        # otherwise fall back to full MediaPipe segmentation mask
        selected_id = int(item.get('effect_selected_person', -1))
        if selected_id >= 0 or selected_id == -2:
            mask = self._get_selected_person_mask(frame, item, t=t)
        else:
            mask = self._get_mediapipe_mask(frame)
            # If MediaPipe unavailable, auto-detect center person and generate mask
            if mask is None:
                persons = self._detect_all_persons(frame)
                if persons:
                    # Pick the person closest to frame center
                    cy, cx = h // 2, w // 2
                    best = min(persons, key=lambda p: (
                        (p['center'][0] - cy) ** 2 + (p['center'][1] - cx) ** 2))
                    mask = self._generate_mask_from_bbox(frame, best['bbox'])

        if mask is None:
            return frame

        # Skip effect if mask is empty (person not found in this frame)
        if mask.max() < 0.01:
            return frame

        # Ensure mask matches frame size
        if mask.shape[:2] != (h, w):
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)

        original_mask = mask.copy()
        painting = item.get('effect_mask_painting')
        if painting is not None and item.get('effect_mask_user_edited', False):
            ph, pw = painting.shape[:2]
            if ph != h or pw != w:
                paint_resized = cv2.resize(painting, (w, h), interpolation=cv2.INTER_LINEAR)
            else:
                paint_resized = painting
            mask = mask * np.clip(paint_resized, 0, 1)

        color_name = item.get('effect_color_variation', 'Gold (Default)')
        palette_entry = self.COLOR_PALETTE.get(color_name, ((255, 200, 50), (200, 140, 20)))
        color_inner, color_outer = palette_entry

        if variation == 'ethereal':
            result = self._create_god_ray_effect(frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask)
        elif variation == 'neon':
            result = self._create_ethereal_effect(frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask)
        elif variation == 'spacy_game_rays':
            result = self._create_brilliance_effect(frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask)
        elif variation == 'gabriel_rays':
            result = self._create_kaka_effect(frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask)
        elif variation == 'angel_rays':
            bbox = None
            if selected_id >= 0:
                yolo_persons = self._yolo_track(frame)
                if yolo_persons:
                    for p in yolo_persons:
                        if p['id'] == selected_id:
                            bbox = p['bbox']
                            break
            result = self._create_holy_aura_effect(frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask, bbox)
        else:
            return frame

        # Overlay drawn mask edges on top of result (outside inv_mask, so always visible)
        drawn = item.get('effect_drawn_mask')
        if drawn is not None and item.get('effect_mask_user_edited', False):
            dh, dw = drawn.shape[:2]
            if dh != h or dw != w:
                drawn_resized = cv2.resize(drawn, (w, h), interpolation=cv2.INTER_LINEAR)
            else:
                drawn_resized = drawn
            drawn_u8 = (np.clip(drawn_resized, 0, 1) * 255).astype(np.uint8)
            de = cv2.Canny(drawn_u8, 20, 80)
            de = cv2.dilate(de, np.ones((2, 2), np.uint8), iterations=1)
            if de.max() > 0:
                de_f = cv2.GaussianBlur(de, (5, 5), 0).astype(np.float32) / 255.0
                result_f = result.astype(np.float32)
                color_f = np.array(color_inner, dtype=np.float32)
                result_f += de_f[..., np.newaxis] * color_f * float(glow) * float(time_factor) * 3.0
                result = np.clip(result_f, 0, 255).astype(np.uint8)

        return result

    def _get_person_outline_edges(self, frame, bbox):
        h, w = frame.shape[:2]
        return self._get_mediapipe_edges(frame)

    def _get_subject_mask(self, frame, cy, cx, bbox=None):
        mask = self._get_mediapipe_mask(frame)
        if mask is not None:
            return mask
        h, w = frame.shape[:2]
        mask = np.zeros((h, w), dtype=np.float32)
        cx_r, cy_r = w // 2, h // 2
        ax, ay = max(1.0, w * 0.25), max(1.0, h * 0.35)
        Y_m, X_m = np.mgrid[:h, :w]
        ellipse = ((X_m - cx_r) / ax) ** 2 + ((Y_m - cy_r) / ay) ** 2
        mask = np.exp(-ellipse / 2.0).astype(np.float32)
        return mask

    def _get_person_edges(self, frame, bbox, cy=None, cx=None):
        return self._get_mediapipe_edges(frame)

    def _get_person_gradient(self, h, w, cy, cx, bbox=None):
        Y, X = np.mgrid[:h, :w]
        diag = np.sqrt(w * w + h * h)
        dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) / (diag * 0.2)
        person_grad = np.exp(-dist ** 2 / 2.0)
        return person_grad

    def _get_subject_outline(self, subject_mask, frame=None, bbox=None):
        return self._get_mediapipe_edges(frame) if frame is not None else np.zeros_like(subject_mask)

    def _get_outline_from_mask(self, mask, expand=20, blur=8):
        mask_uint8 = (np.clip(mask, 0, 1) * 255).astype(np.uint8)
        edges = cv2.Canny(mask_uint8, 30, 90)
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=max(1, expand // 4))
        if blur > 0:
            edges = cv2.GaussianBlur(edges, (blur * 2 + 1, blur * 2 + 1), 0)
        return edges.astype(np.float32) / 255.0

    def _generate_god_rays(self, h, w, cy, cx, intensity=1.0, num_rays=24, spread=1.0):
        return np.zeros((h, w), dtype=np.float32)

    def _generate_gold_rays(self, h, w, cy, cx, intensity=1.0, num_rays=18):
        return np.zeros((h, w), dtype=np.float32)

    def _apply_gold_rim(self, img, frame, h, w, cy, cx, subject_mask, person_edges, opacity, glow, time_factor):
        return img

    def _apply_gold_glow(self, img, frame, h, w, cy, cx, subject_mask, person_edges, opacity, glow, time_factor):
        bg_mask = (1.0 - subject_mask[..., np.newaxis])
        person_grad = self._get_person_gradient(h, w, cy, cx, None)
        glow_color = np.array([1.0, 0.85, 0.0], dtype=np.float32).reshape(1, 1, 3)
        img = img + person_grad[..., np.newaxis] * glow_color * 180.0 * glow * time_factor * bg_mask

        rays = self._generate_gold_rays(h, w, cy, cx, intensity=glow * time_factor * 0.5, num_rays=14)
        ray_color = np.array([1.0, 0.84, 0.0], dtype=np.float32).reshape(1, 1, 3)
        rays_3ch = rays[..., np.newaxis] * ray_color * 100.0
        img = img + rays_3ch * bg_mask

        gold_color = np.array([1.0, 0.84, 0.0], dtype=np.float32).reshape(1, 1, 3)
        img = img + person_edges[..., np.newaxis] * gold_color * 350.0 * glow * time_factor

        return img

    def _apply_gold_halo(self, img, frame, h, w, cy, cx, subject_mask, person_edges, opacity, glow, time_factor):
        bg_mask = (1.0 - subject_mask[..., np.newaxis])
        Y, X = np.mgrid[:h, :w]
        dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
        diag = np.sqrt(w * w + h * h)
        dist_norm = dist / (diag * 0.5)
        dark_mask = np.exp(-dist_norm ** 2 / (2 * 0.3 ** 2))[..., np.newaxis]
        crush = 1.0 - (1.0 - dark_mask) * 0.5 * opacity * time_factor
        img = img * crush

        halo_y = int(cy * 0.6)
        dx = (X - cx).astype(np.float32)
        dy = (Y - halo_y).astype(np.float32)
        halo_dist = np.sqrt(dx ** 2 + dy ** 2)
        halo_dist_norm = halo_dist / (diag * 0.25)
        halo_ring = np.exp(-((halo_dist_norm - 0.45) ** 2) / (2 * 0.08 ** 2))
        halo_color = np.array([1.0, 0.85, 0.0], dtype=np.float32).reshape(1, 1, 3)
        img = img + halo_ring[..., np.newaxis] * halo_color * 280.0 * glow * time_factor * bg_mask

        gold_color = np.array([1.0, 0.84, 0.0], dtype=np.float32).reshape(1, 1, 3)
        img = img + person_edges[..., np.newaxis] * gold_color * 400.0 * glow * time_factor

        return img
