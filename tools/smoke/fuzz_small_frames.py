"""Smoke-test every effect and title theme at small frame sizes."""
from __future__ import annotations

import traceback

import numpy as np

from videomerger.effects import EFFECTS, apply_effect
from videomerger.titles import render_lower_third, render_title_card

THEMES = [
    "Cinematic – Deep Space Stars",
    "Cinematic – Light Speed Burst",
    "Cinematic – Travelling Lens Flare",
    "Cinematic – Aurora",
]
STYLES = [
    "Static Aurora Tile (Bracket)",
    "News Headline",
    "Purple Designer Box",
    "Magical Aurora",
]


def main() -> int:
    for width, height in [(32, 32), (48, 64), (160, 120), (640, 360)]:
        frame = np.full((height, width, 3), 90, dtype=np.uint8)
        mask = np.zeros((height, width), dtype=np.float32)
        mask[height // 4:3 * height // 4, width // 4:3 * width // 4] = 1.0
        face = (width // 8, height // 8, max(8, width // 3), max(8, height // 3))
        bbox = (width // 8, height // 8, max(8, width // 3), max(8, height // 3))
        contexts = {
            "gold_outline": {"mask": mask},
            "thug_life": {"face": face},
            "motion_track": {"bbox": bbox},
        }
        for effect_id in EFFECTS:
            try:
                result = apply_effect(
                    frame, effect_id, {}, time=1.3, context=contexts.get(effect_id)
                )
                assert result.shape == frame.shape, (effect_id, result.shape)
                assert result.dtype == np.uint8, (effect_id, result.dtype)
            except Exception:
                print(f"FAIL effect {effect_id} at {width}x{height}")
                traceback.print_exc()
                return 1

    for width, height in [(64, 36), (160, 90), (320, 180)]:
        for theme in THEMES:
            first = render_title_card(width, height, "A", "b", theme, time=0.7, duration=3.0)
            second = render_title_card(width, height, "A", "b", theme, time=1.2, duration=3.0)
            assert first.shape == (height, width, 3), (theme, first.shape)
            assert not np.array_equal(first, second), f"static title theme: {theme}"
        for style in STYLES:
            overlay = render_lower_third("Caption", width, height, style, time=0.4, duration=2.0)
            assert overlay.size == (width, height)

    print("fuzz-ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
