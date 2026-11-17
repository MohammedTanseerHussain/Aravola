"""Arrow + name label that points at a tracked person."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..vision.segmentation import detect_persons
from .three_d_text import _font  # reuse the font resolver

_COLORS = {
    "Yellow": (255, 225, 40),
    "Red": (240, 50, 50),
    "Green": (60, 230, 90),
    "Blue": (60, 150, 255),
    "White": (255, 255, 255),
    "Orange": (255, 150, 40),
    "Cyan": (60, 240, 240),
    "Magenta": (255, 70, 220),
    "Lime": (170, 255, 60),
    "Gold": (255, 200, 60),
}


def _rgba(color: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
    return int(color[0]), int(color[1]), int(color[2]), int(alpha)


def _draw_arrow(layer: Image.Image, cx: float, tip_y: float, color, size: float, length: float) -> None:
    draw = ImageDraw.Draw(layer)
    arrow_w = max(14, int(42 * size))
    arrow_h = max(18, int(52 * size * length))
    shaft_w = max(4, int(arrow_w * 0.22))
    top = tip_y - arrow_h
    # Down-pointing triangle head.
    draw.polygon(
        [(cx, tip_y), (cx - arrow_w / 2, top), (cx + arrow_w / 2, top)],
        fill=_rgba(color),
    )
    # Shaft above the head.
    shaft_top = top - arrow_h * 0.7
    x0, x1 = cx - shaft_w / 2, cx + shaft_w / 2
    y0, y1 = shaft_top, top + 2
    if x1 > x0 and y1 > y0:
        radius = max(0, min(shaft_w // 2, int((x1 - x0) / 2) - 1, int((y1 - y0) / 2)))
        draw.rounded_rectangle(
            [x0, y0, x1, y1],
            radius=radius,
            fill=_rgba(color),
        )
    # Dark inner line for contrast.
    draw.line([(cx, top + 2), (cx, tip_y - arrow_h * 0.25)], fill=(0, 0, 0, 70), width=max(1, shaft_w // 3))


def _bbox_from_center(center: tuple[int, int], frame_shape: tuple[int, int]) -> tuple[int, int, int, int]:
    h, w = frame_shape
    cy, cx = center
    bw, bh = int(w * 0.18), int(h * 0.35)
    return cx - bw // 2, cy - bh // 2, bw, bh


def apply_motion_track(
    frame: np.ndarray,
    *,
    center: tuple[int, int] | None = None,
    bbox: tuple[int, int, int, int] | None = None,
    name: str = "",
    mode: str = "arrow_and_name",
    color: str = "Yellow",
    text_color: str = "Yellow",
    arrow_size: float = 1.0,
    arrow_length: float = 1.0,
    text_size: float = 1.0,
    offset_y: float = 0.0,
    time: float = 0.0,
    track_id: int | None = None,
) -> np.ndarray:
    """Draw a tracking arrow above a person box."""
    if frame is None or frame.size == 0:
        return frame
    h, w = frame.shape[:2]

    if bbox is None:
        if center is None:
            people = detect_persons(frame)
            if not people:
                return frame
            if track_id is not None:
                people = [p for p in people if p.id == track_id] or people
            person = max(people, key=lambda p: p.bbox[2] * p.bbox[3])
            bbox = person.bbox
        else:
            bbox = _bbox_from_center(center, (h, w))

    x, y, bw, bh = bbox
    cx = x + bw / 2
    bob = 5.0 * math.sin(float(time) * 4.0)
    tip_y = max(30.0, y - 10 + float(offset_y) + bob)
    arrow_color = _COLORS.get(color, _COLORS["Yellow"])
    label_color = _COLORS.get(text_color, _COLORS["Yellow"])

    base = Image.fromarray(frame).convert("RGBA")
    arrow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    _draw_arrow(arrow_layer, cx, tip_y, arrow_color, arrow_size, arrow_length)

    # Soft glow behind the arrow.
    glow = arrow_layer.filter(ImageFilter.GaussianBlur(max(2, int(5 * arrow_size))))
    base = Image.alpha_composite(base, glow)
    base = Image.alpha_composite(base, arrow_layer)

    if mode != "arrow_only" and name:
        font = _font(int(max(14, h * 0.035 * text_size)))
        probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        text_box = probe.textbbox((0, 0), name, font=font)
        tw, th = text_box[2] - text_box[0], text_box[3] - text_box[1]
        pad_x, pad_y = int(h * 0.018), int(h * 0.010)
        label_w, label_h = tw + pad_x * 2, th + pad_y * 2
        lx = int(cx - label_w / 2)
        ly = int(tip_y - label_h - max(18, int(52 * arrow_size * arrow_length)) - int(h * 0.012))
        lx = max(2, min(lx, w - label_w - 2))
        ly = max(2, ly)
        label = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(label)
        draw.rounded_rectangle(
            [lx, ly, lx + label_w, ly + label_h],
            radius=max(4, int(label_h * 0.22)),
            fill=(0, 0, 0, 175),
            outline=_rgba(label_color, 220),
            width=max(1, int(h * 0.0025)),
        )
        draw.text((lx + pad_x, ly + pad_y - text_box[1]), name, font=font, fill=_rgba(label_color, 255))
        base = Image.alpha_composite(base, label)

    return np.array(base.convert("RGB"))
