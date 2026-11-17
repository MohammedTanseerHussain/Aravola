"""3D extruded text overlaid in perspective.

The text is rendered once into a canonical RGBA texture, then perspective
warped onto a user-controllable quad.  This mirrors the legacy desktop effect
while keeping the API simple: pass a normalised quad (0..1) or use the default
centred placement.
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_COLORS = {
    "Orange": ((255, 120, 0), (200, 80, 0), (160, 60, 0)),
    "White": ((255, 255, 255), (220, 220, 220), (180, 180, 180)),
    "Gold": ((255, 215, 0), (218, 165, 32), (180, 130, 20)),
    "Red": ((230, 40, 40), (180, 20, 20), (130, 10, 10)),
    "Blue": ((40, 100, 230), (20, 60, 180), (10, 40, 130)),
    "Cyan": ((0, 220, 240), (0, 170, 190), (0, 120, 140)),
    "Green": ((40, 200, 60), (20, 150, 30), (10, 100, 15)),
    "Purple": ((160, 50, 220), (120, 30, 170), (80, 15, 120)),
    "Black": ((60, 60, 60), (40, 40, 40), (25, 25, 25)),
}

_FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\arialbd.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]

_TEXTURE_CACHE: dict[tuple, Image.Image] = {}
_CANON_FONT_PX = 220


def _font(px: int):
    for candidate in _FONT_CANDIDATES:
        try:
            if candidate.exists():
                return ImageFont.truetype(str(candidate), max(8, int(px)))
        except Exception:
            continue
    return ImageFont.load_default()


def _render_texture(text: str, color_name: str, depth: float, style: str, time: float) -> Image.Image:
    colors = _COLORS.get(color_name, _COLORS["Orange"])
    face_color, side_color, dark_color = colors
    font = _font(_CANON_FONT_PX)
    probe = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    bbox = ImageDraw.Draw(probe).textbbox((0, 0), text or " ", font=font)
    text_w = max(1, bbox[2] - bbox[0])
    text_h = max(1, bbox[3] - bbox[1])
    pixel_depth = max(0, int(depth * _CANON_FONT_PX * 0.5))
    pad = int(_CANON_FONT_PX * 0.35) + pixel_depth + 4
    canvas = Image.new("RGBA", (text_w + pad * 2, text_h + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    ax, ay = pad - bbox[0], pad - bbox[1]

    if pixel_depth > 0:
        layers = min(max(1, pixel_depth), 40)
        for index in range(layers - 1, -1, -1):
            ratio = index / max(1, layers)
            color = (
                int(side_color[0] * (0.4 + 0.6 * (1.0 - ratio))),
                int(side_color[1] * (0.4 + 0.6 * (1.0 - ratio))),
                int(side_color[2] * (0.4 + 0.6 * (1.0 - ratio))),
                255,
            )
            draw.text((ax + index, ay + index), text, font=font, fill=color)

    draw.text((ax, ay), text, font=font, fill=(*face_color, 255))

    style_l = (style or "Solid Matte").lower()
    if style_l in {"glossy", "metallic"}:
        highlight = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        hd = ImageDraw.Draw(highlight)
        hd.text((ax, ay - max(1, _CANON_FONT_PX // 40)), text, font=font, fill=(255, 255, 255, 90))
        canvas = Image.alpha_composite(canvas, highlight)
    if style_l == "glow":
        glow = canvas.filter(ImageFilter.GaussianBlur(max(2, _CANON_FONT_PX // 30)))
        # Pulse the glow so the effect is visibly animated.
        boost = 0.55 + 0.25 * math.sin(time * 3.0)
        alpha = glow.getchannel("A").point(lambda v: int(v * boost))
        glow.putalpha(alpha)
        canvas = Image.alpha_composite(Image.new("RGBA", canvas.size, (0, 0, 0, 0)), glow)
        canvas = Image.alpha_composite(canvas, _render_texture(text, color_name, depth, "Solid Matte", 0.0))
    if depth > 0:
        # Dark edge line for separation.
        draw = ImageDraw.Draw(canvas)
        draw.text((ax + pixel_depth, ay + pixel_depth), text, font=font, fill=(*dark_color, 60))
    return canvas


def _texture(text: str, color_name: str, depth: float, style: str, time: float) -> Image.Image:
    key = (text, color_name, round(depth, 3), style, round(time, 2) if style == "Glow" else 0.0)
    cached = _TEXTURE_CACHE.get(key)
    if cached is not None:
        return cached
    texture = _render_texture(text, color_name, depth, style, time)
    if len(_TEXTURE_CACHE) > 16:
        _TEXTURE_CACHE.pop(next(iter(_TEXTURE_CACHE)))
    _TEXTURE_CACHE[key] = texture
    return texture


def default_quad(width: int, height: int) -> list[list[float]]:
    """A centred quad in pixel coordinates."""
    half_w = width * 0.26
    half_h = height * 0.075
    cx, cy = width / 2, height / 2
    return [
        [cx - half_w, cy - half_h],
        [cx + half_w, cy - half_h],
        [cx + half_w, cy + half_h],
        [cx - half_w, cy + half_h],
    ]


def _absolute_quad(quad, width: int, height: int) -> np.ndarray:
    if quad is None:
        points = default_quad(width, height)
    else:
        points = []
        for point in quad:
            x, y = float(point[0]), float(point[1])
            if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                x, y = x * width, y * height
            points.append([x, y])
        if len(points) != 4:
            points = default_quad(width, height)
    return np.asarray(points, dtype=np.float32)


def _shadow_quad(quad: np.ndarray, dx: float, dy: float) -> np.ndarray:
    return quad + np.array([dx, dy], dtype=np.float32)


def apply_3d_text(
    frame: np.ndarray,
    *,
    text: str = "TRACKING",
    color: str = "Orange",
    depth: float = 0.4,
    shadow: float = 0.5,
    style: str = "Solid Matte",
    quad=None,
    time: float = 0.0,
    duration: float = 3.0,
    camera_speed: float = 0.0,
    fade: float = 0.3,
) -> np.ndarray:
    """Warp a 3D text texture onto ``quad`` and composite it over ``frame``."""
    if frame is None or frame.size == 0 or not text:
        return frame
    h, w = frame.shape[:2]
    progress = max(0.0, min(1.0, float(time) / max(1e-6, duration)))

    # Fade in/out.  ``duration`` is the visible window, so time is local.
    alpha = 1.0
    if fade > 0:
        fade = min(float(fade), duration / 2)
        if time < fade:
            alpha = time / max(1e-6, fade)
        elif time > duration - fade:
            alpha = max(0.0, (duration - time) / max(1e-6, fade))
    if alpha <= 0:
        return frame

    dst = _absolute_quad(quad, w, h)
    if camera_speed and camera_speed > 0:
        # Move the quad toward the viewer as the clip progresses.
        scale = 1.0 + min(0.35, camera_speed * 0.006 * progress)
        center = dst.mean(axis=0)
        dst = (dst - center) * scale + center

    texture = _texture(text, color, depth, style, time)
    src = np.array(
        [[0, 0], [texture.width, 0], [texture.width, texture.height], [0, texture.height]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        np.array(texture),
        transform,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )

    base = frame.astype(np.float32)
    if shadow > 0:
        shadow_transform = cv2.getPerspectiveTransform(src, _shadow_quad(dst, w * 0.006, h * 0.012))
        shadow_layer = cv2.warpPerspective(
            np.full((texture.height, texture.width), 255, dtype=np.uint8),
            shadow_transform,
            (w, h),
            flags=cv2.INTER_LINEAR,
        )
        shadow_layer = cv2.GaussianBlur(shadow_layer, (0, 0), max(1.0, min(h, w) * 0.006))
        shadow_alpha = (shadow_layer.astype(np.float32) / 255.0) * float(shadow) * alpha
        base = base * (1.0 - shadow_alpha[..., None] * 0.7)

    rgb = warped[:, :, :3].astype(np.float32)
    a = (warped[:, :, 3].astype(np.float32) / 255.0) * alpha
    base = base * (1.0 - a[..., None]) + rgb * a[..., None]
    return np.clip(base, 0, 255).astype(np.uint8)


def color_names() -> list[str]:
    return list(_COLORS)
