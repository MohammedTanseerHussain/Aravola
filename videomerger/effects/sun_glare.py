"""Warm cinematic sun glare with lens-flare chain."""
from __future__ import annotations

import numpy as np
import cv2
import PIL.Image
from PIL import ImageDraw, ImageFont, ImageFilter


_SUN_GLARE_POSITIONS = {
    'top left':     (0.10, 0.10),
    'top right':    (0.90, 0.10),
    'bottom left':  (0.10, 0.90),
    'bottom right': (0.90, 0.90),
    'center':       (0.50, 0.50),
}

def create_sun_glare(frame, variation='Cinematic', position='Top Left',
                              intensity=1.0, size=1.0, speed=0.3, time_factor=0.0):
    h, w = frame.shape[:2]
    combined = frame.astype(np.float32)
    diag = float(np.hypot(w, h))
    t = time_factor * speed

    key = str(position).strip().lower().replace('_', ' ')
    sx_f, sy_f = _SUN_GLARE_POSITIONS.get(key, (0.10, 0.10))
    sun_x, sun_y = sx_f * w, sy_f * h
    opp_x, opp_y = w - sun_x, h - sun_y

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = xx - sun_x
    dy = yy - sun_y
    dist = np.sqrt(dx * dx + dy * dy)

    glare_layer = np.zeros_like(combined)

    if variation == 'Golden Hour':
        # --- GOLDEN HOUR (image 2): soft warm golden glow, subtle horizontal flare ---
        haze_r = diag * 0.7 * size
        haze_ell = np.sqrt((dx / (haze_r * 1.3)) ** 2 + (dy / (haze_r * 0.8)) ** 2)
        haze = np.clip(1.0 - haze_ell, 0, 1) ** 2.5
        haze_color = np.array([220, 160, 80], dtype=np.float32)
        glare_layer += haze[..., np.newaxis] * haze_color * (0.55 * intensity)

        glow_r = diag * 0.28 * size
        glow_ell = np.sqrt((dx / (glow_r * 1.05)) ** 2 + (dy / (glow_r * 0.95)) ** 2)
        glow = np.clip(1.0 - glow_ell, 0, 1) ** 2.0
        glow_color = np.array([255, 200, 120], dtype=np.float32)
        glare_layer += glow[..., np.newaxis] * glow_color * (0.6 * intensity)

        angle = np.arctan2(dy, dx)
        n_rays = 12
        ray_layer = np.zeros((h, w), dtype=np.float32)
        for i in range(n_rays):
            ray_angle = (2.0 * np.pi * i / n_rays) + t * 0.2
            ang_diff = np.abs(np.arctan2(np.sin(angle - ray_angle), np.cos(angle - ray_angle)))
            ray_w = 0.04 + 0.02 * np.sin(t * 0.3 + i * 1.3)
            spoke = np.clip(1.0 - ang_diff / ray_w, 0, 1) ** 1.5
            falloff = np.clip(1.0 - dist / (diag * 0.55 * size), 0, 1) ** 1.0
            ray_layer += spoke * falloff * (0.5 + 0.5 * np.sin(t * 0.3 + i * 0.7))
        ray_color = np.array([255, 210, 140], dtype=np.float32)
        glare_layer += ray_layer[..., np.newaxis] * ray_color * (0.25 * intensity)

        core_r = diag * 0.06 * size
        pulse = 1.0 + 0.02 * np.sin(t * np.pi * 1.0)
        r_outer = np.sqrt((dx / (core_r * pulse * 2.0)) ** 2 + (dy / (core_r * pulse * 1.8)) ** 2)
        core_outer = np.clip(1.0 - r_outer, 0, 1) ** 1.6
        core_outer_col = np.array([255, 210, 130], dtype=np.float32)
        glare_layer += core_outer[..., np.newaxis] * core_outer_col * (0.7 * intensity)
        r_inner = np.sqrt((dx / (core_r * pulse * 0.9)) ** 2 + (dy / (core_r * pulse * 0.8)) ** 2)
        core_inner = np.clip(1.0 - r_inner, 0, 1) ** 2.2
        core_inner_col = np.array([255, 245, 220], dtype=np.float32)
        glare_layer += core_inner[..., np.newaxis] * core_inner_col * (0.85 * intensity)

        flare_y = sun_y
        flare_dy = np.abs(yy - flare_y)
        flare_width = max(h * 0.008 * size, 2)
        flare_line = np.clip(1.0 - flare_dy / flare_width, 0, 1) ** 2.0
        flare_falloff = np.clip(1.0 - np.abs(xx - sun_x) / (w * 0.8), 0, 1) ** 1.5
        flare_layer = flare_line * flare_falloff
        flare_color = np.array([255, 220, 150], dtype=np.float32)
        glare_layer += flare_layer[..., np.newaxis] * flare_color * (0.35 * intensity)

        blur_k = max(3, int(min(h, w) * 0.025)) | 1
        glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

    elif variation == 'Natural':
        # --- NATURAL: bright white midday sun with white rays & circle bokeh spots ---
        # Cool white ambient haze
        haze_r = diag * 0.55 * size
        haze_ell = np.sqrt((dx / (haze_r * 1.15)) ** 2 + (dy / (haze_r * 0.85)) ** 2)
        haze = np.clip(1.0 - haze_ell, 0, 1) ** 2.4
        haze_color = np.array([200, 200, 210], dtype=np.float32)
        glare_layer += haze[..., np.newaxis] * haze_color * (0.40 * intensity)

        # White outer glow
        glow_r = diag * 0.25 * size
        glow_ell = np.sqrt((dx / (glow_r * 1.05)) ** 2 + (dy / (glow_r * 0.95)) ** 2)
        glow = np.clip(1.0 - glow_ell, 0, 1) ** 2.0
        glow_color = np.array([255, 255, 255], dtype=np.float32)
        glare_layer += glow[..., np.newaxis] * glow_color * (0.50 * intensity)

        # Crisp white radiating rays — many, thin, bright
        angle = np.arctan2(dy, dx)
        n_rays = 24
        ray_layer = np.zeros((h, w), dtype=np.float32)
        for i in range(n_rays):
            ray_angle = (2.0 * np.pi * i / n_rays) + t * 0.15
            ang_diff = np.abs(np.arctan2(np.sin(angle - ray_angle), np.cos(angle - ray_angle)))
            ray_w = 0.012 + 0.008 * np.sin(t * 0.5 + i * 0.9)
            spoke = np.clip(1.0 - ang_diff / ray_w, 0, 1) ** 2.5
            falloff = np.clip(1.0 - dist / (diag * 0.6 * size), 0, 1) ** 0.7
            ray_layer += spoke * falloff * (0.5 + 0.5 * np.sin(t * 0.4 + i * 1.1))
        ray_color = np.array([255, 255, 255], dtype=np.float32)
        glare_layer += ray_layer[..., np.newaxis] * ray_color * (0.45 * intensity)

        # Bright white sun core — tight, intense
        core_r = diag * 0.045 * size
        pulse = 1.0 + 0.02 * np.sin(t * np.pi * 1.2)
        r_outer = np.sqrt((dx / (core_r * pulse * 1.6)) ** 2 + (dy / (core_r * pulse * 1.5)) ** 2)
        core_outer = np.clip(1.0 - r_outer, 0, 1) ** 2.0
        core_outer_col = np.array([255, 255, 255], dtype=np.float32)
        glare_layer += core_outer[..., np.newaxis] * core_outer_col * (0.85 * intensity)
        r_inner = np.sqrt((dx / (core_r * pulse * 0.7)) ** 2 + (dy / (core_r * pulse * 0.65)) ** 2)
        core_inner = np.clip(1.0 - r_inner, 0, 1) ** 3.0
        core_inner_col = np.array([255, 255, 255], dtype=np.float32)
        glare_layer += core_inner[..., np.newaxis] * core_inner_col * (1.0 * intensity)

        # Circle bokeh spots along light axis — round, white-to-warm, varied sizes
        axis_dx = opp_x - sun_x
        axis_dy = opp_y - sun_y
        axis_len = max(np.sqrt(axis_dx ** 2 + axis_dy ** 2), 1e-3)

        circle_bokeh = [
            (0.22, 0.030, (220, 230, 255), 0.25),
            (0.38, 0.020, (255, 255, 255), 0.18),
            (0.50, 0.045, (200, 220, 255), 0.35),
            (0.65, 0.025, (255, 255, 255), 0.20),
            (0.78, 0.038, (210, 225, 255), 0.28),
        ]

        circle_mask = np.zeros((h, w), dtype=np.float32)
        circle_colour = np.zeros((h, w, 3), dtype=np.float32)

        for i, (t_pos, r_frac, color, alpha_base) in enumerate(circle_bokeh):
            cx = sun_x + axis_dx * t_pos + 1.5 * np.sin(t * 0.3 + i * 0.7)
            cy = sun_y + axis_dy * t_pos + 1.2 * np.cos(t * 0.25 + i * 0.5)
            radius = max(diag * r_frac * size, 3)

            d_dist = np.sqrt((cx - sun_x) ** 2 + (cy - sun_y) ** 2)
            fade = np.clip(1.0 - d_dist / (diag * 1.0), 0.3, 1.0)
            alpha = np.clip(alpha_base * fade * intensity, 0.0, 1.0)

            cv2.circle(circle_mask, (int(cx), int(cy)), int(radius), alpha, -1, lineType=cv2.LINE_AA)
            cv2.circle(circle_colour, (int(cx), int(cy)), int(radius), color, -1, lineType=cv2.LINE_AA)

        cblur = max(int(min(h, w) * 0.010) | 1, 3)
        circle_mask = cv2.GaussianBlur(circle_mask, (cblur, cblur), 0)
        circle_colour = cv2.GaussianBlur(circle_colour, (cblur, cblur), 0)
        cmask3 = circle_mask[..., np.newaxis]
        glare_layer += circle_colour * cmask3

        blur_k = max(3, int(min(h, w) * 0.018)) | 1
        glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

    elif variation == 'Sky Burst':
        # --- SKY BURST: natural long-ray sunburst with creamish yellow tones ---
        haze_r = diag * 0.8 * size
        haze_ell = np.sqrt((dx / (haze_r * 1.1)) ** 2 + (dy / (haze_r * 0.9)) ** 2)
        haze = np.clip(1.0 - haze_ell, 0, 1) ** 2.6
        haze_color = np.array([255, 235, 180], dtype=np.float32)
        glare_layer += haze[..., np.newaxis] * haze_color * (0.45 * intensity)

        glow_r = diag * 0.18 * size
        glow_ell = np.sqrt((dx / (glow_r * 1.0)) ** 2 + (dy / (glow_r * 1.0)) ** 2)
        glow = np.clip(1.0 - glow_ell, 0, 1) ** 2.0
        glow_color = np.array([255, 240, 200], dtype=np.float32)
        glare_layer += glow[..., np.newaxis] * glow_color * (0.65 * intensity)

        angle = np.arctan2(dy, dx)
        n_rays = 16
        ray_layer = np.zeros((h, w), dtype=np.float32)
        for i in range(n_rays):
            ray_angle = (2.0 * np.pi * i / n_rays) + t * 0.25
            ang_diff = np.abs(np.arctan2(np.sin(angle - ray_angle), np.cos(angle - ray_angle)))
            ray_w = 0.008 + 0.005 * np.sin(t * 0.4 + i * 1.1)
            spoke = np.clip(1.0 - ang_diff / ray_w, 0, 1) ** 2.8
            falloff = np.clip(1.0 - dist / (diag * 0.85 * size), 0, 1) ** 0.6
            ray_layer += spoke * falloff * (0.5 + 0.5 * np.sin(t * 0.35 + i * 0.8))
        ray_color = np.array([255, 225, 150], dtype=np.float32)
        glare_layer += ray_layer[..., np.newaxis] * ray_color * (0.55 * intensity)

        core_r = diag * 0.05 * size
        pulse = 1.0 + 0.015 * np.sin(t * np.pi * 1.0)
        r_outer = np.sqrt((dx / (core_r * pulse * 1.5)) ** 2 + (dy / (core_r * pulse * 1.5)) ** 2)
        core_outer = np.clip(1.0 - r_outer, 0, 1) ** 2.0
        core_outer_col = np.array([255, 245, 200], dtype=np.float32)
        glare_layer += core_outer[..., np.newaxis] * core_outer_col * (0.85 * intensity)
        r_inner = np.sqrt((dx / (core_r * pulse * 0.6)) ** 2 + (dy / (core_r * pulse * 0.6)) ** 2)
        core_inner = np.clip(1.0 - r_inner, 0, 1) ** 3.0
        core_inner_col = np.array([255, 255, 240], dtype=np.float32)
        glare_layer += core_inner[..., np.newaxis] * core_inner_col * (1.0 * intensity)

        blur_k = max(3, int(min(h, w) * 0.015)) | 1
        glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

    else:
        # --- CINEMATIC (image 1): dramatic rays, orange hex bokeh, teal accents ---
        glow_r = diag * 0.35 * size
        glow_elliptical = np.sqrt((dx / (glow_r * 1.1)) ** 2 + (dy / (glow_r * 0.9)) ** 2)
        glow = np.clip(1.0 - glow_elliptical, 0, 1) ** 2.2
        glow_color = np.array([255, 145, 35], dtype=np.float32)
        glare_layer += glow[..., np.newaxis] * glow_color * (0.7 * intensity)

        haze_r = diag * 0.6 * size
        haze_elliptical = np.sqrt((dx / (haze_r * 1.2)) ** 2 + (dy / (haze_r * 0.85)) ** 2)
        haze = np.clip(1.0 - haze_elliptical, 0, 1) ** 2.8
        haze_color = np.array([180, 70, 15], dtype=np.float32)
        glare_layer += haze[..., np.newaxis] * haze_color * (0.45 * intensity)

        angle = np.arctan2(dy, dx)
        n_rays = 18
        ray_layer_r = np.zeros((h, w), dtype=np.float32)
        for i in range(n_rays):
            ray_angle = (2.0 * np.pi * i / n_rays) + t * 0.4
            ang_diff = np.abs(np.arctan2(np.sin(angle - ray_angle), np.cos(angle - ray_angle)))
            ray_w = 0.02 + 0.015 * np.sin(t * 0.7 + i * 1.1)
            spoke = np.clip(1.0 - ang_diff / ray_w, 0, 1) ** 2.0
            falloff = np.clip(1.0 - dist / (diag * 0.5 * size), 0, 1) ** 0.8
            ray_layer_r += spoke * falloff * (0.4 + 0.6 * np.sin(t * 0.5 + i * 0.9))
        ray_color = np.array([255, 200, 110], dtype=np.float32)
        glare_layer += ray_layer_r[..., np.newaxis] * ray_color * (0.35 * intensity)

        core_r = diag * 0.055 * size
        pulse = 1.0 + 0.03 * np.sin(t * np.pi * 1.5)
        r_outer = np.sqrt((dx / (core_r * pulse * 1.8)) ** 2 + (dy / (core_r * pulse * 1.6)) ** 2)
        core_outer = np.clip(1.0 - r_outer, 0, 1) ** 1.8
        core_outer_col = np.array([255, 180, 60], dtype=np.float32)
        glare_layer += core_outer[..., np.newaxis] * core_outer_col * (0.8 * intensity)
        r_inner = np.sqrt((dx / (core_r * pulse)) ** 2 + (dy / (core_r * pulse * 0.9)) ** 2)
        core_inner = np.clip(1.0 - r_inner, 0, 1) ** 2.5
        core_inner_col = np.array([255, 240, 210], dtype=np.float32)
        glare_layer += core_inner[..., np.newaxis] * core_inner_col * (0.9 * intensity)

        axis_dx = opp_x - sun_x
        axis_dy = opp_y - sun_y
        axis_len = max(np.sqrt(axis_dx ** 2 + axis_dy ** 2), 1e-3)

        bokeh = [
            (0.20, 0.035, (255, 200,  90), 0.30),
            (0.30, 0.060, (255, 140,  50), 0.40),
            (0.38, 0.030, (255, 220, 130), 0.28),
            (0.46, 0.075, (230,  90,  30), 0.45),
            (0.54, 0.025, (255, 170,  70), 0.25),
            (0.62, 0.065, (255, 130,  45), 0.42),
            (0.70, 0.040, (255, 200, 110), 0.32),
            (0.78, 0.080, (240, 100,  35), 0.50),
            (0.86, 0.045, (255, 180,  90), 0.35),
        ]

        hex_mask = np.zeros((h, w), dtype=np.float32)
        hex_colour = np.zeros((h, w, 3), dtype=np.float32)

        for i, (t_pos, r_frac, color, alpha_base) in enumerate(bokeh):
            cx = sun_x + axis_dx * t_pos + 2.0 * np.sin(t * 0.4 + i * 0.8)
            cy = sun_y + axis_dy * t_pos + 1.5 * np.cos(t * 0.35 + i * 0.6)
            radius = max(diag * r_frac * size, 4)
            rot = t * 1.0 + i * 0.35

            pts = []
            for v in range(6):
                a = np.radians(60 * v + rot)
                pts.append([int(cx + radius * np.cos(a)),
                            int(cy + radius * np.sin(a))])
            pts = np.array(pts, dtype=np.int32)

            d = np.sqrt((cx - sun_x) ** 2 + (cy - sun_y) ** 2)
            fade = np.clip(1.0 - d / (diag * 1.1), 0.3, 1.0)
            alpha = np.clip(alpha_base * fade * intensity, 0.0, 1.0)

            cv2.fillPoly(hex_mask, [pts], alpha, lineType=cv2.LINE_AA)
            cv2.fillPoly(hex_colour, [pts], color, lineType=cv2.LINE_AA)

        blur_r = max(int(min(h, w) * 0.008) | 1, 3)
        hex_mask = cv2.GaussianBlur(hex_mask, (blur_r, blur_r), 0)
        hex_colour = cv2.GaussianBlur(hex_colour, (blur_r, blur_r), 0)
        mask3 = hex_mask[..., np.newaxis]
        glare_layer += hex_colour * mask3

        flare_y = sun_y
        flare_dy = np.abs(yy - flare_y)
        flare_width = max(h * 0.003 * size, 1)
        flare_line = np.clip(1.0 - flare_dy / flare_width, 0, 1) ** 3.0
        flare_falloff = np.clip(1.0 - np.abs(xx - sun_x) / (w * 0.9), 0, 1) ** 2.0
        flare_layer = flare_line * flare_falloff
        flare_color = np.array([255, 180, 80], dtype=np.float32)
        glare_layer += flare_layer[..., np.newaxis] * flare_color * (0.45 * intensity)

        teal_x, teal_y = opp_x * 0.4 + sun_x * 0.6, opp_y * 0.3 + sun_y * 0.7
        teal_dx = xx - teal_x
        teal_dy = yy - teal_y
        teal_r = diag * 0.18 * size
        teal_ell = np.sqrt((teal_dx / (teal_r * 1.4)) ** 2 + (teal_dy / (teal_r * 0.7)) ** 2)
        teal = np.clip(1.0 - teal_ell, 0, 1) ** 2.0
        teal_color = np.array([60, 200, 210], dtype=np.float32)
        glare_layer += teal[..., np.newaxis] * teal_color * (0.20 * intensity)

        blur_k = max(3, int(min(h, w) * 0.020)) | 1
        glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

    # Screen blend onto the frame — adds light, never crushes blacks
    glare_norm = glare_layer / 255.0
    base_norm = combined / 255.0
    screen = 1.0 - (1.0 - base_norm) * (1.0 - glare_norm)
    combined = screen * 255.0

    return np.clip(combined, 0, 255).astype(np.uint8)

def apply_sun_glare(frame, *, variation="Cinematic", position="Top Left",
                    intensity=1.0, size=1.0, speed=0.3, time=0.0):
    """Public wrapper. ``time`` is the effect-local time in seconds."""
    return create_sun_glare(frame, variation=variation, position=position,
                            intensity=intensity, size=size, speed=speed,
                            time_factor=time)
