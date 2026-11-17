"""Title cards, lower thirds and text overlays.

The legacy GUI built these as MoviePy clips with ImageMagick.  This module
renders them with Pillow/NumPy so they work in a headless container and can be
used both for preview stills and as ``fl_image`` overlays during export.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\arialbd.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        try:
            if candidate.exists():
                return ImageFont.truetype(str(candidate), max(8, int(size)))
        except Exception:
            continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return max(1, box[2] - box[0]), max(1, box[3] - box[1])


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if _text_size(draw, trial, font)[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _gradient(width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> np.ndarray:
    ramp = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
    top_arr = np.array(top, dtype=np.float32).reshape(1, 1, 3)
    bottom_arr = np.array(bottom, dtype=np.float32).reshape(1, 1, 3)
    return np.repeat(top_arr * (1.0 - ramp) + bottom_arr * ramp, width, axis=1)


def _radial_glow(width: int, height: int, cx: float, cy: float, radius: float,
                 color: tuple[int, int, int], strength: float = 1.0) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    dist = np.sqrt(((xx - cx) / max(1.0, radius)) ** 2 + ((yy - cy) / max(1.0, radius)) ** 2)
    mask = np.clip(1.0 - dist, 0.0, 1.0) ** 2.0
    return mask[..., None] * np.array(color, dtype=np.float32) * strength


def _stars(width: int, height: int, count: int = 160, seed: int = 7,
           time: float = 0.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    layer = np.zeros((height, width, 3), dtype=np.float32)
    xs = rng.integers(0, width, count)
    ys = rng.integers(0, height, count)
    twinkle = 0.62 + 0.38 * np.sin(
        time * 2.4 + rng.uniform(0.0, 2.0 * math.pi, count)
    )
    brightness = rng.uniform(80, 255, count) * twinkle
    for x, y, value in zip(xs, ys, brightness):
        layer[y, x] = np.clip(layer[y, x] + value, 0, 255)
    return layer


def _aurora(width: int, height: int, time: float = 0.0) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    x = xx / max(1, width)
    y = yy / max(1, height)
    wave1 = 0.5 + 0.5 * np.sin(6.0 * x + 1.8 * time)
    wave2 = 0.5 + 0.5 * np.sin(9.0 * x - 1.1 * time + 1.7)
    band = np.exp(-((y - (0.35 + 0.10 * wave1)) ** 2) / (2 * 0.10 ** 2))
    band2 = np.exp(-((y - (0.55 + 0.08 * wave2)) ** 2) / (2 * 0.14 ** 2))
    green = np.array([40, 220, 150], dtype=np.float32)
    violet = np.array([120, 70, 230], dtype=np.float32)
    out = band[..., None] * green * 0.55 + band2[..., None] * violet * 0.45
    return out


def _background(theme: str, width: int, height: int, time: float) -> np.ndarray:
    theme_l = (theme or "").lower()
    if "deep space" in theme_l or "stars" in theme_l:
        base = _gradient(width, height, (4, 6, 30), (18, 8, 50))
        drift = 0.03 * math.sin(time * 0.5)
        base += _radial_glow(width, height, width * (0.72 + drift), height * 0.30,
                             width * 0.55, (70, 40, 170), 0.35)
        base += _stars(width, height, 180, seed=11, time=time)
        return np.clip(base, 0, 255)
    if "light speed" in theme_l or "burst" in theme_l:
        base = _gradient(width, height, (8, 8, 16), (20, 10, 28))
        base += _radial_glow(width, height, width * 0.5, height * 0.5, width * 0.55,
                             (255, 190, 80), 0.55 + 0.05 * math.sin(time * 2.0))
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        angle = np.arctan2(yy - height / 2, xx - width / 2)
        rays = (0.5 + 0.5 * np.cos(angle * 18 + time * 1.4)) ** 10
        dist = np.sqrt(((xx - width / 2) / width) ** 2 + ((yy - height / 2) / height) ** 2)
        base += (rays * np.clip(1.0 - dist * 1.7, 0, 1))[..., None] * np.array([255, 180, 90], dtype=np.float32) * 0.6
        return np.clip(base, 0, 255)
    if "flare" in theme_l or "travelling" in theme_l:
        base = _gradient(width, height, (8, 10, 18), (30, 14, 20))
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        pos = 0.15 + 0.7 * ((time * 0.08) % 1.0)
        cx = width * pos
        cy = height * (0.25 + 0.12 * math.sin(time * 0.7))
        base += _radial_glow(width, height, cx, cy, width * 0.45, (255, 150, 60), 0.8)
        streak = np.exp(-((yy - (0.25 * height + 0.55 * yy)) / (height * 0.05)) ** 2)
        base += streak[..., None] * np.array([255, 190, 90], dtype=np.float32) * 0.20
        return np.clip(base, 0, 255)
    if "aurora" in theme_l:
        base = _gradient(width, height, (2, 12, 24), (4, 28, 36))
        base += _aurora(width, height, time)
        base += _stars(width, height, 100, seed=21, time=time) * 0.5
        return np.clip(base, 0, 255)
    return _gradient(width, height, (10, 10, 18), (28, 18, 40))


def _draw_centered_text(
    image: Image.Image,
    main_text: str,
    sub_text: str = "",
    *,
    main_ratio: float = 0.11,
    sub_ratio: float = 0.038,
    color: tuple[int, int, int] = (255, 245, 220),
    accent: tuple[int, int, int] = (255, 190, 70),
    offset_y: float = 0.0,
    opacity: float = 1.0,
) -> Image.Image:
    if opacity <= 0:
        return image
    width, height = image.size
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    main_font = _font(int(height * main_ratio))
    sub_font = _font(int(height * sub_ratio))
    max_width = int(width * 0.82)
    lines = _wrap(draw, main_text or "", main_font, max_width)
    line_heights = [_text_size(draw, line, main_font)[1] for line in lines]
    total_h = sum(line_heights) + max(0, len(lines) - 1) * int(height * 0.02)
    sub_h = _text_size(draw, sub_text or "", sub_font)[1] if sub_text else 0
    block_h = total_h + (int(height * 0.025) + sub_h if sub_text else 0)
    y = (height - block_h) / 2 + height * offset_y
    for line, line_h in zip(lines, line_heights):
        line_w = _text_size(draw, line, main_font)[0]
        draw.text(((width - line_w) / 2, y), line, font=main_font, fill=(*color, int(255 * opacity)))
        y += line_h + int(height * 0.02)
    if sub_text:
        y += int(height * 0.012)
        sub_w = _text_size(draw, sub_text, sub_font)[0]
        draw.text(((width - sub_w) / 2, y), sub_text, font=sub_font, fill=(*accent, int(235 * opacity)))

    glow = layer.filter(ImageFilter.GaussianBlur(max(2, int(height * 0.008))))
    base = image.convert("RGBA")
    base = Image.alpha_composite(base, glow)
    base = Image.alpha_composite(base, layer)
    return base.convert("RGB")


def render_title_card(
    width: int,
    height: int,
    main_text: str = "TITLE",
    sub_text: str = "",
    theme: str = "Cinematic – Deep Space Stars",
    *,
    time: float = 0.0,
    duration: float = 5.0,
) -> np.ndarray:
    """Render one title-card frame as RGB uint8."""
    bg = _background(theme, width, height, time)
    image = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
    progress = max(0.0, min(1.0, time / max(1e-6, duration)))
    fade = min(1.0, progress / 0.18, (1.0 - progress) / 0.18) if duration > 1.0 else 1.0
    fade = max(0.0, min(1.0, fade))
    image = _draw_centered_text(image, main_text, sub_text, opacity=fade)
    return np.array(image)


def _rounded_rectangle(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def render_lower_third(
    text: str,
    width: int,
    height: int,
    style: str = "Static Aurora Tile (Bracket)",
    *,
    time: float = 0.0,
    duration: float = 3.0,
) -> Image.Image:
    """Render a transparent RGBA lower-third overlay."""
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    if not text:
        return overlay

    progress = max(0.0, min(1.0, time / max(1e-6, duration)))
    slide = min(1.0, progress / 0.18) if progress < 0.18 else (1.0 if progress < 0.82 else max(0.0, (1.0 - progress) / 0.18))
    slide = max(0.0, min(1.0, slide))
    font = _font(int(height * 0.045))
    text_w, text_h = _text_size(draw, text, font)
    pad_x = int(width * 0.035)
    pad_y = int(height * 0.022)
    box_w = min(int(width * 0.78), text_w + pad_x * 2)
    box_h = text_h + pad_y * 2
    x = int(width * 0.06 - (1.0 - slide) * width * 0.15)
    y = int(height * 0.76)

    style_l = (style or "").lower()
    if "news" in style_l:
        draw.rectangle([x, y, x + box_w, y + box_h], fill=(180, 20, 30, 225))
        draw.rectangle([x, y, x + int(width * 0.008), y + box_h], fill=(255, 220, 80, 255))
        draw.text((x + pad_x, y + pad_y), text, font=font, fill=(255, 255, 255, 245))
    elif "purple" in style_l or "designer" in style_l:
        _rounded_rectangle(draw, [x, y, x + box_w, y + box_h], int(box_h * 0.22),
                           fill=(78, 20, 120, 225), outline=(190, 120, 255, 230), width=max(1, int(height * 0.003)))
        draw.text((x + pad_x, y + pad_y), text, font=font, fill=(245, 230, 255, 250))
    elif "bracket" in style_l or "tile" in style_l:
        draw.rectangle([x, y, x + box_w, y + box_h], fill=(8, 12, 20, 190), outline=(0, 200, 255, 220), width=max(1, int(height * 0.003)))
        bracket = int(box_h * 0.35)
        draw.line([x, y, x + bracket, y], fill=(255, 220, 100, 255), width=max(2, int(height * 0.006)))
        draw.line([x, y, x, y + bracket], fill=(255, 220, 100, 255), width=max(2, int(height * 0.006)))
        draw.text((x + pad_x, y + pad_y), text, font=font, fill=(255, 250, 235, 250))
    elif "aurora" in style_l:
        grad = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        for i in range(box_h):
            alpha = int(225 * (0.55 + 0.45 * math.sin(i / max(1, box_h) * math.pi)))
            gd.line([(0, i), (box_w, i)], fill=(20, 180, 150, alpha))
        overlay.alpha_composite(grad, (x, y))
        draw.text((x + pad_x, y + pad_y), text, font=font, fill=(255, 255, 255, 250))
    else:  # default bracket / tile
        draw.rectangle([x, y, x + box_w, y + box_h], fill=(8, 12, 20, 190), outline=(0, 200, 255, 220), width=max(1, int(height * 0.003)))
        bracket = int(box_h * 0.35)
        draw.line([x, y, x + bracket, y], fill=(255, 220, 100, 255), width=max(2, int(height * 0.006)))
        draw.line([x, y, x, y + bracket], fill=(255, 220, 100, 255), width=max(2, int(height * 0.006)))
        draw.text((x + pad_x, y + pad_y), text, font=font, fill=(255, 250, 235, 250))
    return overlay


def composite_lower_third(
    frame: np.ndarray,
    text: str,
    style: str = "Static Aurora Tile (Bracket)",
    *,
    time: float = 0.0,
    duration: float = 3.0,
) -> np.ndarray:
    height, width = frame.shape[:2]
    overlay = render_lower_third(text, width, height, style, time=time, duration=duration)
    base = Image.fromarray(frame).convert("RGBA")
    base = Image.alpha_composite(base, overlay)
    return np.array(base.convert("RGB"))


def overlay_plain_text(
    frame: np.ndarray,
    text: str,
    *,
    position: str = "bottom",
    opacity: float = 1.0,
) -> np.ndarray:
    """Simple caption overlay used for clip ``text`` properties."""
    if not text or opacity <= 0:
        return frame
    h, w = frame.shape[:2]
    image = Image.fromarray(frame).convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _font(max(14, int(h * 0.045)))
    lines = _wrap(draw, text, font, int(w * 0.86))
    line_h = _text_size(draw, "Ag", font)[1]
    block_h = line_h * len(lines) + int(h * 0.02)
    y = int(h * 0.90) - block_h if position == "bottom" else int(h * 0.07)
    draw.rectangle([int(w * 0.04), y - int(h * 0.012), int(w * 0.96), y + block_h + int(h * 0.012)],
                   fill=(0, 0, 0, int(120 * opacity)))
    for line in lines:
        draw.text((int(w * 0.06), y), line, font=font, fill=(255, 255, 255, int(255 * opacity)))
        y += line_h
    return np.array(Image.alpha_composite(image, layer).convert("RGB"))
