"""Anamorphic X-shaped cross flare."""
from __future__ import annotations

import numpy as np
import cv2
import PIL.Image
from PIL import ImageDraw, ImageFont, ImageFilter


_X_FLARE_POSITIONS = {
    'top left':     (0.15, 0.15),
    'top right':    (0.85, 0.15),
    'bottom left':  (0.15, 0.85),
    'bottom right': (0.85, 0.85),
    'center':       (0.50, 0.50),
}

_X_FLARE_COLORS = {
    'Blue White':   {'ray': (200, 220, 255), 'core': (255, 255, 255), 'glow': (140, 180, 255), 'fringe': (180, 140, 255)},
    'Purple Haze':  {'ray': (200, 160, 255), 'core': (240, 220, 255), 'glow': (180, 100, 255), 'fringe': (255, 120, 200)},
    'Golden Cross': {'ray': (255, 230, 160), 'core': (255, 250, 230), 'glow': (255, 200, 100), 'fringe': (255, 180, 80)},
    'Ice White':    {'ray': (230, 240, 255), 'core': (255, 255, 255), 'glow': (200, 220, 255), 'fringe': (160, 200, 240)},
}

def create_x_flare(frame, variation='Blue White', position='Center',
                           intensity=1.0, size=1.0, speed=0.3, time_factor=0.0):
    h, w = frame.shape[:2]
    combined = frame.astype(np.float32)
    diag = float(np.hypot(w, h))
    t = time_factor * speed

    # Camera flash flicker — rapid irregular brightness pulses
    flicker = (0.7
               + 0.30 * np.sin(t * 18.0)
               + 0.15 * np.sin(t * 31.0)
               + 0.10 * np.sin(t * 47.0)
               + 0.08 * np.sin(t * 73.0))
    flicker = max(flicker, 0.15)
    intensity = intensity * flicker

    key = str(position).strip().lower().replace('_', ' ')
    fx_f, fy_f = _X_FLARE_POSITIONS.get(key, (0.50, 0.50))
    cx, cy = fx_f * w, fy_f * h

    colors = _X_FLARE_COLORS.get(variation, _X_FLARE_COLORS['Blue White'])
    ray_col = np.array(colors['ray'], dtype=np.float32)
    core_col = np.array(colors['core'], dtype=np.float32)
    glow_col = np.array(colors['glow'], dtype=np.float32)
    fringe_col = np.array(colors['fringe'], dtype=np.float32)

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = xx - cx
    dy = yy - cy
    dist = np.sqrt(dx * dx + dy * dy)

    glare_layer = np.zeros_like(combined)
    angle = np.arctan2(dy, dx)

    # --- 4 glowing X rays — bright near source, fading to tips ---
    arm_angles = [np.pi / 4, 3 * np.pi / 4, 5 * np.pi / 4, 7 * np.pi / 4]
    ray_len = diag * 0.42 * size
    ray_half_w = 0.022 * size
    ray_glow_w = 0.06 * size

    ray_layer = np.zeros((h, w), dtype=np.float32)
    glow_layer = np.zeros((h, w), dtype=np.float32)

    for arm_a in arm_angles:
        ang_diff = np.abs(np.arctan2(np.sin(angle - arm_a), np.cos(angle - arm_a)))
        ray_core = np.clip(1.0 - ang_diff / ray_half_w, 0, 1) ** 1.5
        ray_soft = np.clip(1.0 - ang_diff / ray_glow_w, 0, 1) ** 2.0
        radial_fade = np.clip(1.0 - dist / ray_len, 0, 1) ** 0.8
        ray_layer = np.maximum(ray_layer, ray_core * radial_fade)
        glow_layer = np.maximum(glow_layer, ray_soft * radial_fade)

    glare_layer += glow_layer[..., np.newaxis] * glow_col * (0.35 * intensity)
    glare_layer += ray_layer[..., np.newaxis] * ray_col * (0.75 * intensity)

    # --- Purple fringing on ray edges ---
    fringe_layer = np.zeros((h, w), dtype=np.float32)
    for arm_a in arm_angles:
        ang_diff = np.abs(np.arctan2(np.sin(angle - arm_a), np.cos(angle - arm_a)))
        fringe_mask = np.clip(1.0 - ang_diff / ray_glow_w, 0, 1) ** 2.0
        fringe_inner = np.clip(1.0 - ang_diff / ray_half_w, 0, 1) ** 1.5
        fringe_band = np.clip(fringe_mask - fringe_inner, 0, 1)
        radial_fade = np.clip(1.0 - dist / ray_len, 0, 1) ** 0.8
        fringe_layer = np.maximum(fringe_layer, fringe_band * radial_fade)
    glare_layer += fringe_layer[..., np.newaxis] * fringe_col * (0.50 * intensity)

    # --- Bright glowing center source ---
    core_r = diag * 0.022 * size
    r_wide = np.sqrt((dx / (core_r * 4.0)) ** 2 + (dy / (core_r * 4.0)) ** 2)
    core_wide = np.clip(1.0 - r_wide, 0, 1) ** 1.4
    glare_layer += core_wide[..., np.newaxis] * glow_col * (0.6 * intensity)
    r_mid = np.sqrt((dx / (core_r * 2.0)) ** 2 + (dy / (core_r * 2.0)) ** 2)
    core_mid = np.clip(1.0 - r_mid, 0, 1) ** 1.8
    glare_layer += core_mid[..., np.newaxis] * core_col * (0.85 * intensity)
    r_inner = np.sqrt((dx / core_r) ** 2 + (dy / core_r) ** 2)
    core_inner = np.clip(1.0 - r_inner, 0, 1) ** 2.2
    glare_layer += core_inner[..., np.newaxis] * core_col * (1.0 * intensity)

    blur_k = max(3, int(min(h, w) * 0.010)) | 1
    glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

    # Screen blend
    glare_norm = glare_layer / 255.0
    base_norm = combined / 255.0
    screen = 1.0 - (1.0 - base_norm) * (1.0 - glare_norm)
    combined = screen * 255.0

    return np.clip(combined, 0, 255).astype(np.uint8)

def apply_x_flare(frame, *, variation="Blue White", position="Center",
                  intensity=1.0, size=1.0, speed=0.3, time=0.0):
    """Public wrapper. ``time`` is the effect-local time in seconds."""
    return create_x_flare(frame, variation=variation, position=position,
                          intensity=intensity, size=size, speed=speed,
                          time_factor=time)
