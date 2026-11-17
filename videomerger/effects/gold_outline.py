"""Glowing subject outline with radiant rays ("gold outline" family).

This is a headless re-implementation of the legacy effect: it takes a person
mask from :mod:`videomerger.vision` and renders a rim, halo and animated rays.
Keeping it mask-in/frame-out makes it easy to test and to combine with any
segmentation backend.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

COLOR_PALETTES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "Gold (Default)": ((255, 205, 60), (205, 135, 15)),
    "Warm Gold": ((255, 230, 140), (220, 160, 40)),
    "Orange": ((255, 150, 40), (210, 80, 10)),
    "Sunset": ((255, 120, 70), (200, 60, 30)),
    "Pink": ((255, 130, 210), (205, 60, 160)),
    "Purple": ((210, 140, 255), (140, 60, 210)),
    "Blue": ((130, 200, 255), (50, 120, 230)),
    "Cyan": ((130, 255, 245), (20, 180, 190)),
    "Green": ((150, 255, 140), (30, 180, 70)),
    "Neon Green": ((170, 255, 90), (40, 210, 30)),
    "White": ((255, 255, 255), (210, 210, 220)),
    "Red": ((255, 100, 100), (200, 30, 30)),
    "Yellow": ((255, 250, 150), (230, 200, 40)),
    "Ice": ((220, 245, 255), (150, 200, 240)),
    "Rose Gold": ((255, 190, 160), (210, 120, 90)),
    "Emerald": ((120, 255, 200), (20, 160, 110)),
    "Sapphire": ((150, 180, 255), (50, 80, 210)),
    "Amethyst": ((220, 160, 255), (150, 70, 220)),
    "Copper": ((255, 170, 110), (190, 90, 40)),
    "Silver": ((240, 240, 250), (170, 170, 190)),
}


def _smooth_mask(mask: np.ndarray) -> np.ndarray:
    mask = np.clip(mask.astype(np.float32), 0.0, 1.0)
    if mask.max() <= 0.001:
        return mask
    blurred = cv2.GaussianBlur(mask, (0, 0), max(1.0, min(mask.shape[:2]) * 0.006))
    return np.clip(blurred, 0.0, 1.0)


def _center_of(mask: np.ndarray) -> tuple[int, int]:
    binary = (mask > 0.5).astype(np.uint8)
    moments = cv2.moments(binary)
    if moments["m00"] > 0:
        return int(moments["m01"] / moments["m00"]), int(moments["m10"] / moments["m00"])
    h, w = mask.shape[:2]
    return h // 2, w // 2


def _radial_rays(
    h: int,
    w: int,
    cy: int,
    cx: int,
    *,
    count: int = 24,
    spread: float = 1.0,
    time: float = 0.0,
    width: float = 0.018,
) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    angle = np.arctan2(yy - cy, xx - cx)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    max_dist = math.hypot(w, h)
    rays = np.zeros((h, w), dtype=np.float32)
    for index in range(count):
        base = (index / count) * math.tau + time * 0.12
        diff = np.abs(np.arctan2(np.sin(angle - base), np.cos(angle - base)))
        ray = np.clip(1.0 - diff / (width * spread), 0, 1) ** 1.4
        fade = np.clip(1.0 - dist / (max_dist * 0.55), 0, 1) ** 0.8
        rays = np.maximum(rays, ray * fade)
    return rays


def apply_gold_outline(
    frame: np.ndarray,
    mask: np.ndarray,
    *,
    variation: str = "ethereal",
    color_name: str = "Gold (Default)",
    color_inner: tuple[int, int, int] | None = None,
    color_outer: tuple[int, int, int] | None = None,
    opacity: float = 0.9,
    glow: float = 1.0,
    time: float = 0.0,
) -> np.ndarray:
    """Overlay a glowing outline + rays around ``mask``."""
    if frame is None or frame.size == 0 or mask is None:
        return frame
    if opacity <= 0 and glow <= 0:
        return frame
    h, w = frame.shape[:2]
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
    mask = _smooth_mask(mask)
    if mask.max() < 0.01:
        return frame

    inner, outer = COLOR_PALETTES.get(color_name, COLOR_PALETTES["Gold (Default)"])
    if color_inner is not None:
        inner = tuple(int(v) for v in color_inner)
    if color_outer is not None:
        outer = tuple(int(v) for v in color_outer)

    binary = (mask > 0.5).astype(np.uint8) * 255
    edges = cv2.Canny(binary, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    edges = cv2.GaussianBlur(edges, (0, 0), max(1.0, min(h, w) * 0.004)).astype(np.float32) / 255.0

    # Rim: a soft band hugging the mask boundary.
    kernel = np.ones((5, 5), np.uint8)
    rim = cv2.dilate(binary, kernel, iterations=2).astype(np.float32) / 255.0
    rim = np.clip(rim - mask, 0, 1)
    rim = cv2.GaussianBlur(rim, (0, 0), max(1.0, min(h, w) * 0.006))

    glow_small = cv2.GaussianBlur(edges, (0, 0), max(1.5, min(h, w) * 0.008)) * 1.4
    glow_large = cv2.GaussianBlur(edges, (0, 0), max(4.0, min(h, w) * 0.030)) * 0.9

    cy, cx = _center_of(mask)
    variation_l = (variation or "ethereal").lower()
    rays = np.zeros((h, w), dtype=np.float32)
    if variation_l in {"ethereal", "angel_rays", "gabriel_rays", "spacy_game_rays"}:
        count = 20 if variation_l == "ethereal" else 28
        spread = 1.0 if variation_l != "gabriel_rays" else 1.6
        rays = _radial_rays(h, w, cy, cx, count=count, spread=spread, time=time)
        if variation_l == "angel_rays":
            # Focus the rays above the head, like a halo fan.
            yy = np.arange(h, dtype=np.float32)[:, None]
            rays *= np.clip(1.0 - (yy - cy) / max(1.0, h * 0.55), 0.0, 1.0)
        if variation_l == "spacy_game_rays":
            rays = np.clip(rays * 1.4, 0, 1)

    # Build a light layer (additive) and a glow layer.
    light = np.zeros((h, w, 3), dtype=np.float32)
    light += rim[..., None] * np.array(inner, dtype=np.float32) * (1.6 * glow)
    light += glow_small[..., None] * np.array(inner, dtype=np.float32) * (1.4 * glow)
    light += glow_large[..., None] * np.array(outer, dtype=np.float32) * (0.9 * glow)
    light += rays[..., None] * np.array(inner, dtype=np.float32) * (0.55 * glow * (0.7 + 0.3 * math.sin(time * 2.0)))

    if variation_l == "neon":
        neon = cv2.GaussianBlur(edges, (0, 0), max(1.0, min(h, w) * 0.012))
        light += neon[..., None] * np.array(inner, dtype=np.float32) * (2.0 * glow)
    elif variation_l == "angel_rays":
        halo_y = max(0, cy - int(h * 0.18))
        halo = np.zeros((h, w), dtype=np.float32)
        cv2.ellipse(halo, (cx, halo_y), (max(10, int(w * 0.10)), max(4, int(h * 0.035))),
                    0, 0, 360, 1.0, -1)
        halo = cv2.GaussianBlur(halo, (0, 0), max(3.0, min(h, w) * 0.012))
        light += halo[..., None] * np.array(inner, dtype=np.float32) * (1.8 * glow)

    base = frame.astype(np.float32) / 255.0
    light_norm = np.clip(light / 255.0, 0.0, 1.0)
    screen = 1.0 - (1.0 - base) * (1.0 - light_norm)
    result = base * (1.0 - opacity) + screen * opacity
    return np.clip(result * 255.0, 0, 255).astype(np.uint8)


def palette_names() -> list[str]:
    return list(COLOR_PALETTES)
