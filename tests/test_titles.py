from __future__ import annotations

import numpy as np

from videomerger.titles import (
    composite_lower_third,
    overlay_plain_text,
    render_lower_third,
    render_title_card,
)


def test_title_card_shape():
    frame = render_title_card(320, 180, "HELLO", "world", time=1.0, duration=3.0)
    assert frame.shape == (180, 320, 3)
    assert frame.dtype == np.uint8


def test_title_card_is_animated():
    a = render_title_card(160, 90, "HELLO", time=1.0, duration=3.0)
    b = render_title_card(160, 90, "HELLO", time=2.0, duration=3.0)
    assert not np.array_equal(a, b)


def test_lower_third_has_visible_pixels():
    overlay = render_lower_third("Breaking news", 320, 180, "News Headline",
                                 time=1.0, duration=3.0)
    assert overlay.mode == "RGBA"
    assert overlay.size == (320, 180)
    assert np.array(overlay)[:, :, 3].max() > 0


def test_composite_lower_third_changes_frame():
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    result = composite_lower_third(frame, "Caption", time=0.5, duration=2.0)
    assert result.shape == frame.shape
    assert result.max() > 0


def test_plain_text_overlay():
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    result = overlay_plain_text(frame, "A caption")
    assert result.shape == frame.shape
    assert result.max() > 0
