"""Ken Burns (zoom / pan) applied to an RGB frame."""
from __future__ import annotations

import numpy as np
import cv2
import PIL.Image
from PIL import ImageDraw, ImageFont, ImageFilter


def apply_kenburns(frame, zoom, pan_x, pan_y, t_prog, target_w, target_h):
    """Zooms/pans an already frame-sized (target_w x target_h) RGB
    array — used to apply Ken Burns *after* the 3D text has been
    composited into the frame, so the text zooms/pans together with
    the scene (staying pinned to the same point in it) instead of
    sitting fixed on screen while the video moves underneath it."""
    if zoom <= 1.0001 and pan_x == 0 and pan_y == 0:
        return frame
    img = PIL.Image.fromarray(frame)
    new_w = max(1, int(round(target_w * zoom)))
    new_h = max(1, int(round(target_h * zoom)))
    big = img.resize((new_w, new_h), PIL.Image.LANCZOS)
    offset_x = pan_x * target_w * 0.5 * t_prog
    offset_y = pan_y * target_h * 0.5 * t_prog
    cx = new_w / 2.0 + offset_x
    cy = new_h / 2.0 + offset_y
    left = int(round(cx - target_w / 2.0))
    top = int(round(cy - target_h / 2.0))
    left = max(0, min(left, max(0, new_w - target_w)))
    top = max(0, min(top, max(0, new_h - target_h)))
    cropped = big.crop((left, top, left + target_w, top + target_h))
    if cropped.size != (target_w, target_h):
        canvas = PIL.Image.new("RGB", (target_w, target_h), (0, 0, 0))
        canvas.paste(cropped, (0, 0))
        cropped = canvas
    return np.array(cropped)
