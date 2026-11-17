"""Fog + volumetric god-ray canopy overlay."""
from __future__ import annotations

import numpy as np
import cv2
import PIL.Image
from PIL import ImageDraw, ImageFont, ImageFilter


_CANOPY_LIGHT_DIRS = {
    'top left':     (0.20, 0.05),
    'top right':    (0.80, 0.05),
    'top center':   (0.50, 0.0),
    'behind':       (0.50, 0.30),
    'side left':    (0.05, 0.45),
    'side right':   (0.95, 0.45),
}

def create_canopy(frame, light_dir='Top Left', light_style='Soft Atmosphere',
                          fog_density=0.7, fog_height=0.5, ray_intensity=1.0, ray_width=1.0,
                          warmth=0.7, shimmer=0.3, time_factor=0.0,
                          person_mask=None, show_light_source=True):
    h, w = frame.shape[:2]
    combined = frame.astype(np.float32)

    key = str(light_dir).strip().lower().replace('_', ' ')
    lx, ly = _CANOPY_LIGHT_DIRS.get(key, (0.20, 0.05))
    src_x, src_y = lx * w, ly * h

    t = time_factor
    diag = float(np.hypot(w, h))

    flicker = 1.0
    if shimmer > 0:
        flicker = (1.0
                   + shimmer * 0.08 * np.sin(t * 3.7)
                   + shimmer * 0.05 * np.sin(t * 7.1)
                   + shimmer * 0.03 * np.sin(t * 13.3))

    # ── WARM LIGHT COLOR (shifts with warmth slider) ──
    warm_r = min(255, int(220 + warmth * 35))
    warm_g = min(255, int(200 + warmth * 40))
    warm_b = min(255, int(180 + warmth * 30))
    ray_color = np.array([warm_r, warm_g, warm_b], dtype=np.float32)

    # ── COORDINATE GRID ──
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = xx - src_x
    dy = yy - src_y
    dist = np.sqrt(dx**2 + dy**2)

    # ════════════════════════════════════════════════════════════════
    #  LAYERED FOG — multiple depth bands like mountain valleys
    # ════════════════════════════════════════════════════════════════
    fog_y = yy / h

    # Deep valley fog (bottom third, dense)
    fog_deep = np.clip((fog_y - (1.0 - fog_height * 0.5)) / (fog_height * 0.5), 0, 1) ** 1.8

    # Mid-level mist (middle band, wispy)
    mid_band = np.clip(1.0 - np.abs(fog_y - 0.55) / 0.20, 0, 1)
    fog_mid = mid_band ** 2.0

    # High-altitude haze (thin, near top)
    high_band = np.clip(1.0 - np.abs(fog_y - 0.25) / 0.15, 0, 1)
    fog_high = high_band ** 2.5 * 0.4

    # Horizontal wisps (sinusoidal variation across width)
    wisp1 = 0.5 + 0.5 * np.sin(xx * 2 * np.pi / max(w * 0.35, 1.0) + 1.2)
    wisp2 = 0.5 + 0.5 * np.sin(xx * 2 * np.pi / max(w * 0.55, 1.0) + 3.8)
    wisp3 = 0.5 + 0.5 * np.sin(xx * 2 * np.pi / max(w * 0.2, 1.0) - 0.5)

    fog_mask = (fog_deep * (0.65 + 0.35 * wisp1) +
                fog_mid * (0.5 + 0.5 * wisp2) * 0.55 +
                fog_high * (0.7 + 0.3 * wisp3))

    # Attenuate fog near the light source (light burns through)
    light_dist_norm = np.clip(dist / diag, 0, 1)
    fog_mask *= np.clip(1.0 - np.exp(-light_dist_norm ** 2 / (2 * 0.25**2)), 0.2, 1.0)

    fog_t = np.clip(fog_mask * fog_density, 0, 1)
    # Color gradient: lighter near light source, darker in shadows
    fog_near = np.array([min(255, warm_r + 10), min(255, warm_g + 5), min(255, warm_b)], dtype=np.float32)
    fog_far = np.array([140, 150, 170], dtype=np.float32)
    fog_proximity = np.clip(1.0 - light_dist_norm * 0.7, 0, 1)
    fog_color = fog_far.reshape(1, 1, 3) * (1.0 - fog_proximity[..., np.newaxis]) + \
                fog_near.reshape(1, 1, 3) * fog_proximity[..., np.newaxis]
    fog_layer = fog_color * fog_t[..., np.newaxis]
    fog_alpha = np.clip(fog_t * 0.6 * fog_density, 0, 0.6)
    combined = combined * (1.0 - fog_alpha[..., np.newaxis]) + fog_layer * fog_alpha[..., np.newaxis]

    # ════════════════════════════════════════════════════════════════
    #  GOD RAYS — style-dependent ray rendering
    # ════════════════════════════════════════════════════════════════
    is_behind = 'behind' in key
    if is_behind:
        base_angle = np.pi * 0.5
    elif 'left' in key and 'side' not in key:
        base_angle = np.pi * 0.38
    elif 'right' in key and 'side' not in key:
        base_angle = np.pi * 0.62
    elif 'side left' in key:
        base_angle = np.pi * 0.15
    elif 'side right' in key:
        base_angle = np.pi * 0.85
    else:
        base_angle = np.pi * 0.45

    is_forest = (light_style == 'Forest Rays')

    if is_forest:
        num_rays = 12
        spread_total = 2.6 * ray_width
    else:
        num_rays = 14
        spread_total = 1.1 * ray_width

    ray_layer = np.zeros((h, w, 3), dtype=np.float32)
    ray_strength = np.zeros((h, w), dtype=np.float32)
    ray_spread_angles = np.linspace(-spread_total / 2, spread_total / 2, num_rays)

    for i in range(num_rays):
        ray_angle = base_angle + ray_spread_angles[i]
        rdx = np.cos(ray_angle)
        rdy = np.sin(ray_angle)
        cross = dx * rdy - dy * rdx

        if is_forest:
            ray_w_px = (45 + (i % 4) * 20) * ray_width
            ray_falloff = np.exp(-0.5 * (np.abs(cross) / max(ray_w_px, 1.0))**2.0)
            intensity = 1.0 if i % 4 == 0 else (0.6 if i % 4 == 1 else (0.85 if i % 4 == 2 else 0.4))
        else:
            ray_w_px = (20 + i * 6) * ray_width
            ray_falloff = np.exp(-0.5 * (np.abs(cross) / max(ray_w_px, 1.0))**2)
            intensity = [0.6, 1.0, 0.8, 0.5, 0.9, 0.7, 1.0, 0.6, 0.8, 0.7, 1.0, 0.5, 0.9, 0.6][i]

        along = dx * rdx + dy * rdy
        along_clipped = np.clip(along, 0, diag)

        if is_forest:
            dist_fade = np.clip(1.0 / (1.0 + (along_clipped / (diag * 0.40))**1.2), 0, 1)
            fog_absorb = np.clip(1.0 - fog_mask * 0.35, 0.08, 1.0)
        else:
            dist_fade = np.clip(1.0 / (1.0 + along_clipped / (diag * 0.35)), 0, 1)
            fog_absorb = np.clip(1.0 - fog_mask * 0.35, 0.15, 1.0)

        this_ray = ray_falloff * dist_fade * fog_absorb * flicker * intensity
        ray_strength = np.maximum(ray_strength, this_ray)
        if is_forest:
            col_var = ray_color * (0.92 + 0.08 * np.sin(i * 1.7))
        else:
            col_var = ray_color * (0.85 + 0.15 * np.sin(i * 1.7))
        ray_layer += this_ray[..., np.newaxis] * col_var.reshape(1, 1, 3)

    # ── Composite rays onto frame (additive, safe) ──
    ray_strength = np.clip(ray_strength, 0, 1)
    if is_forest:
        ray_alpha = np.clip(ray_strength * ray_intensity * 0.85, 0, 0.95)
    else:
        ray_alpha = np.clip(ray_strength * ray_intensity * 0.55, 0, 0.7)

    ray_rgb = np.clip(ray_layer, 0, 255)
    combined = np.clip(combined + ray_rgb * ray_alpha[..., np.newaxis], 0, 255)

    # ── Core glow (light source — bright hot center like real sun) ──
    if show_light_source:
        if is_forest:
            core_r = diag * 0.06
            core_pow = 2.2
        else:
            core_r = diag * 0.05
            core_pow = 2.5
        core_dist = np.sqrt((dx / max(core_r * 2.0, 1.0))**2 + (dy / max(core_r * 1.4, 1.0))**2)
        core_mask = np.clip(1.0 - core_dist, 0, 1) ** core_pow

        # Bright white-hot center (like real sun), transitioning to warm gold
        hot_center = np.clip(1.0 - core_dist * 0.6, 0, 1) ** 3.0
        hot_color = np.array([255.0, 248.0, 220.0], dtype=np.float32)
        warm_color = np.array([min(255, warm_r + 20), min(255, warm_g + 15), min(255, warm_b + 8)], dtype=np.float32)
        # Inner white-hot glow layer
        combined += hot_center[..., np.newaxis] * hot_color.reshape(1, 1, 3) * 0.7 * ray_intensity * flicker
        # Outer warm glow layer
        core_strength = core_mask * ray_intensity * flicker
        combined += core_strength[..., np.newaxis] * warm_color.reshape(1, 1, 3) * 0.3
        combined = np.clip(combined, 0, 255)

        # ── Wide warm haze around light source ──
        haze_r = diag * 0.20
        haze_dist = np.sqrt((dx / max(haze_r, 1.0))**2 + (dy / max(haze_r, 1.0))**2)
        haze_mask = np.clip(1.0 - haze_dist, 0, 1) ** 1.5
        haze_color = np.array([min(255, warm_r + 12), min(255, warm_g + 8), min(255, warm_b)], dtype=np.float32)
        haze_alpha = haze_mask * 0.15 * ray_intensity * flicker
        combined = np.clip(combined + haze_alpha[..., np.newaxis] * haze_color.reshape(1, 1, 3), 0, 255)

    # ── Atmospheric depth tint ──
    depth_tint = np.array([0.03, 0.03, 0.05], dtype=np.float32)
    combined = combined * 0.92 + (combined + depth_tint.reshape(1, 1, 3) * 255.0) * 0.08

    # ════════════════════════════════════════════════════════════════
    #  PERSON INTEGRATION — light wraps around borders from behind
    # ════════════════════════════════════════════════════════════════
    if person_mask is not None and person_mask.max() > 0.01:
        pm = person_mask
        if pm.shape[:2] != (h, w):
            pm = cv2.resize(pm, (w, h), interpolation=cv2.INTER_LINEAR)

        pm_u8 = (np.clip(pm, 0, 1) * 255).astype(np.uint8)
        person_edges = cv2.Canny(pm_u8, 25, 85)
        person_edges = cv2.dilate(person_edges, np.ones((2, 2), np.uint8), iterations=1)
        person_edges = cv2.GaussianBlur(person_edges, (5, 5), 0).astype(np.float32) / 255.0

        # Dilated outer edge (soft glow zone around the person)
        outer_dilated = cv2.dilate(pm_u8, np.ones((11, 11), np.uint8), iterations=1)
        outer_glow = cv2.GaussianBlur(outer_dilated, (21, 21), 0).astype(np.float32) / 255.0
        outer_glow = outer_glow * (1.0 - pm)

        # Person centroid for ray origin
        ys, xs = np.where(pm > 0.3)
        if len(xs) > 0:
            cy_p = int(np.mean(ys))
            cx_p = int(np.mean(xs))
        else:
            cy_p, cx_p = h // 2, w // 2

        bg_mask = (1.0 - pm)[..., np.newaxis]

        # ── RIM LIGHT — light source direction wraps around person ──
        # Compute signed distance from light direction through person center
        rim_angle = np.arct2(src_y - cy_p, src_x - cx_p)
        rim_dir_x = np.cos(rim_angle)
        rim_dir_y = np.sin(rim_angle)

        Y_r, X_r = np.mgrid[:h, :w].astype(np.float32)
        # Positive = facing light source (lit side), negative = away (shadow side)
        rim_dot = (X_r - cx_p) * rim_dir_x + (Y_r - cy_p) * rim_dir_y
        rim_sdf = cv2.GaussianBlur(rim_dot.astype(np.float32), (0, 0), 15)
        rim_lit = np.clip(rim_sdf, 0, 1)
        rim_shadow = np.clip(-rim_sdf, 0, 1)

        # Inner edge rim — warm light on the lit side of the silhouette
        rim_inner = rim_lit * person_edges * 1.5
        rim_inner = np.clip(rim_inner, 0, 1)
        rim_color = np.array([min(255, warm_r + 10), min(255, warm_g + 5), warm_b], dtype=np.float32)
        combined += rim_inner[..., np.newaxis] * rim_color.reshape(1, 1, 3) * 0.3 * ray_intensity * flicker

        # Outer edge rim — soft golden glow on lit side outline
        outer_edges = cv2.dilate(pm_u8, np.ones((7, 7), np.uint8), iterations=1)
        outer_edges = cv2.GaussianBlur(outer_edges, (9, 9), 0).astype(np.float32) / 255.0
        outer_edges *= (1.0 - pm)
        rim_outer = outer_edges * rim_lit * 1.2
        gold_rim = np.array([1.0, 0.82, 0.0], dtype=np.float32)
        combined += rim_outer[..., np.newaxis] * gold_rim.reshape(1, 1, 3) * 80.0 * ray_intensity * flicker * bg_mask

        # Subtle shadow-side darkening for depth
        shadow_depth = rim_shadow * pm * 0.15 * ray_intensity
        combined *= (1.0 - shadow_depth[..., np.newaxis])

        # ── BEHIND MODE — light emanates from borders of the person ──
        if is_behind:
            # Soft backlit rim along the silhouette edge
            backlit_rim = person_edges * 1.8
            backlit_rim = np.clip(backlit_rim, 0, 1)
            backlight_color = np.array([min(255, warm_r + 15), min(255, warm_g + 8), min(255, warm_b + 3)], dtype=np.float32)
            combined += backlit_rim[..., np.newaxis] * backlight_color.reshape(1, 1, 3) * 0.5 * ray_intensity * flicker

            # Wider soft glow around the silhouette
            wide_glow = cv2.dilate(pm_u8, np.ones((15, 15), np.uint8), iterations=1)
            wide_glow = cv2.GaussianBlur(wide_glow, (25, 25), 0).astype(np.float32) / 255.0
            wide_glow *= (1.0 - pm)
            combined += wide_glow[..., np.newaxis] * gold_rim.reshape(1, 1, 3) * 60.0 * ray_intensity * flicker * bg_mask

            # Soft rays emanating outward from silhouette
            Y_p, X_p = np.mgrid[:h, :w].astype(np.float32)
            pdx = X_p - cx_p
            pdy = Y_p - cy_p
            p_diag = np.hypot(w, h)

            edge_rays = np.zeros((h, w, 3), dtype=np.float32)
            num_edge_rays = 12
            for j in range(num_edge_rays):
                pa = (j / num_edge_rays) * 2 * np.pi
                rdx_j = np.cos(pa)
                rdy_j = np.sin(pa)
                cross_j = pdx * rdx_j - pdy * rdy_j
                pw_j = 15 + 8 * np.sin(j * 2.1)
                falloff_j = np.exp(-0.5 * (cross_j / max(pw_j, 1.0))**2)
                along_j = np.clip(pdx * rdx_j + pdy * rdy_j, 0, p_diag)
                fade_j = np.clip(1.0 - along_j / (p_diag * 0.35), 0, 1) ** 0.7
                outside_mask = (1.0 - pm)
                edge_rays += (falloff_j * fade_j * outside_mask)[..., np.newaxis] * ray_color.reshape(1, 1, 3)

            combined += edge_rays * 20.0 * ray_intensity * flicker

            # Soft bloom behind the person
            bloom_y = max(0, cy_p - int(h * 0.1))
            bloom_dx = X_p - cx_p
            bloom_dy = Y_p - bloom_y
            bloom_dist = np.sqrt(bloom_dx**2 + bloom_dy**2)
            bloom_r = diag * 0.15
            bloom_mask = np.clip(1.0 - bloom_dist / bloom_r, 0, 1) ** 2.0
            bloom_mask *= outside_mask
            bloom_color = np.array([min(255, warm_r + 5), min(255, warm_g + 3), warm_b], dtype=np.float32)
            combined += bloom_mask[..., np.newaxis] * bloom_color.reshape(1, 1, 3) * 15.0 * ray_intensity * flicker

    return np.clip(combined, 0, 255).astype(np.uint8)

def apply_canopy(frame, *, light_dir="Top Left", light_style="Soft Atmosphere",
                 fog_density=0.7, fog_height=0.5, ray_intensity=1.0,
                 ray_width=1.0, warmth=0.7, shimmer=0.3, time=0.0,
                 person_mask=None, show_light_source=True):
    """Public wrapper. ``time`` is the effect-local time in seconds."""
    return create_canopy(frame, light_dir=light_dir, light_style=light_style,
                         fog_density=fog_density, fog_height=fog_height,
                         ray_intensity=ray_intensity, ray_width=ray_width,
                         warmth=warmth, shimmer=shimmer, time_factor=time,
                         person_mask=person_mask,
                         show_light_source=show_light_source)
