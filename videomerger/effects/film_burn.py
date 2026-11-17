"""Film-burn / scorching light-leak overlay."""
from __future__ import annotations

import numpy as np
import cv2
import PIL.Image
from PIL import ImageDraw, ImageFont, ImageFilter


def create_film_burn(frame, intensity=1.0, speed=1.0, time_factor=0.0):
    h, w = frame.shape[:2]
    combined = frame.astype(np.float32)
    t = time_factor * speed

    # Multiple flare centers that sweep across the frame dynamically
    flare1_x = int(w * (0.1 + 0.8 * ((t * 0.7) % 1.0)))
    flare1_y = int(h * (0.3 + 0.3 * np.sin(t * np.pi * 2.2)))
    flare2_x = int(w * (0.9 - 0.7 * ((t * 0.5) % 1.0)))
    flare2_y = int(h * (0.7 + 0.2 * np.cos(t * np.pi * 3.1)))
    flare3_x = int(w * (0.5 + 0.35 * np.sin(t * np.pi * 1.3)))
    flare3_y = int(h * (0.1 + 0.8 * ((t * 0.35) % 1.0)))
    flare4_x = int(w * (0.2 + 0.6 * np.cos(t * np.pi * 1.8 + 1.0)))
    flare4_y = int(h * (0.5 + 0.4 * np.sin(t * np.pi * 2.7 + 0.5)))

    yy, xx = np.mgrid[0:h, 0:w]

    # --- Flare 1: Large warm orange core ---
    r1 = np.sqrt(((xx - flare1_x) / (w * 0.4))**2 + ((yy - flare1_y) / (h * 0.5))**2)
    flare1 = np.clip(1.0 - r1, 0, 1) ** 1.5
    flare1_color = np.array([255, 150, 20], dtype=np.float32)

    # --- Flare 2: Medium red-hot streak ---
    r2 = np.sqrt(((xx - flare2_x) / (w * 0.3))**2 + ((yy - flare2_y) / (h * 0.35))**2)
    flare2 = np.clip(1.0 - r2, 0, 1) ** 2.0
    flare2_color = np.array([255, 50, 5], dtype=np.float32)

    # --- Flare 3: Small bright yellow-white hotspot ---
    r3 = np.sqrt(((xx - flare3_x) / (w * 0.18))**2 + ((yy - flare3_y) / (h * 0.22))**2)
    flare3 = np.clip(1.0 - r3, 0, 1) ** 2.5
    flare3_color = np.array([255, 230, 100], dtype=np.float32)

    # --- Flare 4: Extra moving flare for more dynamism ---
    r4 = np.sqrt(((xx - flare4_x) / (w * 0.25))**2 + ((yy - flare4_y) / (h * 0.3))**2)
    flare4 = np.clip(1.0 - r4, 0, 1) ** 1.8
    flare4_color = np.array([255, 100, 10], dtype=np.float32)

    # --- Horizontal anamorphic light leak streak ---
    streak_y = int(h * (0.35 + 0.3 * np.sin(t * np.pi * 2.8)))
    streak_mask = np.exp(-((yy - streak_y).astype(np.float32)**2) / (2 * (h * 0.1)**2))
    streak_x_mask = np.clip(1.0 - np.abs(xx - w // 2).astype(np.float32) / (w * 0.5), 0, 1)
    streak = streak_mask * streak_x_mask ** 1.3
    streak_color = np.array([255, 180, 50], dtype=np.float32)

    # --- Edge burn (film burns brightest at edges) ---
    cx, cy = w / 2, h / 2
    dist_from_center = np.sqrt(((xx - cx) / cx)**2 + ((yy - cy) / cy)**2)
    edge_burn = np.clip(dist_from_center - 0.4, 0, 1) ** 1.1
    edge_burn_color = np.array([220, 90, 10], dtype=np.float32)

    # --- Compose all layers (boosted multipliers for brightness) ---
    film_layer = np.zeros_like(combined)
    film_layer += flare1[..., np.newaxis] * flare1_color * (0.9 * intensity)
    film_layer += flare2[..., np.newaxis] * flare2_color * (0.7 * intensity)
    film_layer += flare3[..., np.newaxis] * flare3_color * (1.1 * intensity)
    film_layer += flare4[..., np.newaxis] * flare4_color * (0.65 * intensity)
    film_layer += streak[..., np.newaxis] * streak_color * (0.55 * intensity)
    film_layer += edge_burn[..., np.newaxis] * edge_burn_color * (0.45 * intensity)

    # --- Glow blur for soft diffusion ---
    blur_ksize = max(3, int(min(h, w) * 0.07)) | 1
    film_layer = cv2.GaussianBlur(film_layer, (blur_ksize, blur_ksize), 0)

    # --- Screen blend: brighten without crushing blacks ---
    film_norm = film_layer / 255.0
    base_norm = combined / 255.0
    screen = 1.0 - (1.0 - base_norm) * (1.0 - film_norm * 0.85)
    combined = screen * 255.0

    # --- Warm color grade: push midtones toward amber ---
    combined[:, :, 0] = combined[:, :, 0] * 1.12   # boost red
    combined[:, :, 2] = combined[:, :, 2] * 0.85    # reduce blue

    # --- Fade in/out envelope using intensity as opacity proxy ---
    blend = np.clip(intensity * 0.75, 0.0, 1.0)
    combined = frame.astype(np.float32) * (1.0 - blend) + combined * blend

    return np.clip(combined, 0, 255).astype(np.uint8)

def apply_film_burn(frame, *, intensity=1.0, speed=1.0, time=0.0):
    """Public wrapper. ``time`` is the effect-local time in seconds."""
    return create_film_burn(frame, intensity=intensity, speed=speed, time_factor=time)
