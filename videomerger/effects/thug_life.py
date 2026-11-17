"""Thug-life accessories: sunglasses, gold chain and cap.

The effect is face-box driven: pass a face box from the API, or let the
function detect the largest face with the bundled Haar cascade.  Assets are
loaded from ``assets/accessories`` with fallbacks to the legacy PNGs.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ..config import CAP, CHAIN_PIXEL, CHAIN_REAL, GLASSES_PIXEL, GLASSES_REAL
from ..vision.segmentation import largest_face

_ASSET_CACHE: dict[str, Image.Image | None] = {}


def _load(path: Path | None) -> Image.Image | None:
    if path is None:
        return None
    key = str(path)
    if key in _ASSET_CACHE:
        return _ASSET_CACHE[key]
    try:
        image = Image.open(path).convert("RGBA")
    except Exception:
        image = None
    _ASSET_CACHE[key] = image
    return image


def _resize(asset: Image.Image, width: int, *, smooth: bool) -> Image.Image:
    width = max(1, int(width))
    height = max(1, int(asset.height * width / max(1, asset.width)))
    resampling = Image.LANCZOS if smooth else Image.NEAREST
    return asset.resize((width, height), resampling)


def _apply_override(asset: Image.Image, override: dict | None) -> Image.Image:
    if not override:
        return asset
    scale = float(override.get("scale", 1.0) or 1.0)
    if abs(scale - 1.0) > 1e-6:
        asset = _resize(asset, int(asset.width * scale), smooth=True)
    rotation = float(override.get("rotation", 0.0) or 0.0)
    if abs(rotation) > 0.01:
        asset = asset.rotate(-rotation, expand=True, resample=Image.BICUBIC)
    if override.get("flip_h"):
        asset = asset.transpose(Image.FLIP_LEFT_RIGHT)
    if override.get("flip_v"):
        asset = asset.transpose(Image.FLIP_TOP_BOTTOM)
    return asset


def _paste(base: Image.Image, asset: Image.Image, cx: int, cy: int) -> None:
    left = int(cx - asset.width / 2)
    top = int(cy - asset.height / 2)
    base.alpha_composite(asset, (left, top))


def _ease_out_back(p: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def _entry_offset(entry: str, p: float, width: int, height: int) -> tuple[int, int]:
    remain = 1.0 - p
    entry = (entry or "top").lower()
    if entry == "left":
        return -int(width * 0.8 * remain), 0
    if entry == "right":
        return int(width * 0.8 * remain), 0
    if entry == "bottom":
        return 0, int(height * 0.8 * remain)
    if entry == "rush":
        return int(width * 0.35 * remain), -int(height * 0.35 * remain)
    if entry == "bounce":
        return 0, -int(height * 0.5 * abs(math.sin(remain * math.pi)))
    return 0, -int(height * 0.8 * remain)


def _simple_cap(width: int) -> Image.Image:
    width = max(10, int(width))
    height = max(8, int(width * 0.45))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([0, 0, width - 1, int(height * 0.72)], fill=(18, 18, 20, 245))
    x0, y0 = int(width * 0.08), int(height * 0.18)
    x1, y1 = int(width * 0.92), int(height * 0.52)
    radius = max(0, min(int(height * 0.15), (x1 - x0 - 2) // 2, (y1 - y0 - 2) // 2))
    if radius > 0:
        draw.rounded_rectangle(
            [x0, y0, x1, y1],
            radius=radius,
            fill=(25, 25, 28, 245),
        )
    else:
        draw.rectangle([x0, y0, x1, y1], fill=(25, 25, 28, 245))
    draw.rectangle([int(width * 0.55), int(height * 0.36), width - 1, int(height * 0.58)],
                   fill=(15, 15, 17, 250))
    return image


def apply_thug_life(
    frame: np.ndarray,
    *,
    face: tuple[int, int, int, int] | None = None,
    style: str = "realistic",
    entry: str = "top",
    cap_enabled: bool = True,
    time: float = 0.0,
    glasses_override: dict | None = None,
    chain_override: dict | None = None,
    cap_override: dict | None = None,
) -> np.ndarray:
    """Overlay animated accessories on the largest face (or ``face`` box)."""
    if frame is None or frame.size == 0:
        return frame
    if face is None:
        face = largest_face(frame)
    if face is None:
        return frame
    x, y, fw, fh = [int(v) for v in face]
    h, w = frame.shape[:2]
    x = max(0, min(x, w - 2))
    y = max(0, min(y, h - 2))
    fw = max(8, min(fw, w - x))
    fh = max(8, min(fh, h - y))
    cx = x + fw // 2
    smooth = (style or "realistic").lower() != "pixel"
    progress = max(0.0, min(1.0, float(time) / 0.65))
    eased = _ease_out_back(progress)

    base = Image.fromarray(frame).convert("RGBA")

    glasses_src = _load(GLASSES_REAL if smooth else GLASSES_PIXEL)
    if glasses_src is not None:
        glasses = _resize(glasses_src, int(fw * 1.28), smooth=smooth)
        glasses = _apply_override(glasses, glasses_override)
        dx, dy = _entry_offset(entry, eased, w, h)
        _paste(base, glasses, cx + dx, y + int(fh * 0.40) + dy)

    chain_src = _load(CHAIN_REAL if smooth else CHAIN_PIXEL)
    if chain_src is not None:
        chain = _resize(chain_src, int(fw * 1.55), smooth=smooth)
        chain = _apply_override(chain, chain_override)
        slide = int((1.0 - eased) * fh * 0.9)
        _paste(base, chain, cx, y + int(fh * 1.05) + slide)

    if cap_enabled:
        cap = _load(CAP)
        if cap is None:
            cap = _simple_cap(int(fw * 1.2))
        else:
            cap = _resize(cap, int(fw * 1.2), smooth=smooth)
        cap = _apply_override(cap, cap_override)
        cap_slide = int((1.0 - eased) * fh * 0.7)
        _paste(base, cap, cx, y - int(fh * 0.15) + cap_slide)

    return np.array(base.convert("RGB"))
