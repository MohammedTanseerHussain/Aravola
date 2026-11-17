from __future__ import annotations

import numpy as np
import pytest

from videomerger.effects import EFFECTS, apply_effect, apply_effects, list_effects


SIMPLE_EFFECTS = ["color_filter", "film_burn", "sun_glare", "x_flare", "light_flash",
                  "canopy", "ken_burns"]


def test_registry_lists_every_effect():
    ids = {item["id"] for item in list_effects()}
    assert ids == set(EFFECTS)
    assert len(ids) == 11


@pytest.mark.parametrize("effect_id", SIMPLE_EFFECTS)
def test_simple_effects_preserve_shape_and_dtype(effect_id, frame):
    result = apply_effect(frame, effect_id, {}, time=0.35)
    assert result.shape == frame.shape
    assert result.dtype == np.uint8


def test_advanced_effects_accept_presupplied_context(frame):
    import cv2

    mask = np.zeros(frame.shape[:2], dtype=np.float32)
    cv2.circle(mask, (80, 60), 35, 1.0, -1)
    gold = apply_effect(frame, "gold_outline", {"opacity": 0.8}, time=0.4,
                        context={"mask": mask})
    assert gold.shape == frame.shape

    thug = apply_effect(frame, "thug_life", {"style": "realistic"}, time=0.4,
                        context={"face": (30, 10, 60, 60)})
    assert thug.shape == frame.shape

    text = apply_effect(frame, "three_d_text", {"text": "TEST"}, time=0.4)
    assert text.shape == frame.shape

    track = apply_effect(frame, "motion_track", {"name": "SUBJECT"}, time=0.4,
                         context={"bbox": (40, 20, 60, 90)})
    assert track.shape == frame.shape


def test_advanced_effects_survive_tiny_frames():
    tiny = np.full((32, 32, 3), 90, dtype=np.uint8)
    mask = np.zeros((32, 32), dtype=np.float32)
    mask[8:24, 8:24] = 1.0
    for effect_id, context in (
        ("gold_outline", {"mask": mask}),
        ("thug_life", {"face": (4, 4, 10, 10)}),
        ("motion_track", {"bbox": (4, 4, 10, 10)}),
    ):
        result = apply_effect(tiny, effect_id, {}, time=0.8, context=context)
        assert result.shape == tiny.shape
        assert result.dtype == np.uint8


def test_color_filter_is_deterministic_for_a_given_time(frame):
    a = apply_effect(frame, "color_filter", {"style": "BW Memories"}, time=1.25)
    b = apply_effect(frame, "color_filter", {"style": "BW Memories"}, time=1.25)
    c = apply_effect(frame, "color_filter", {"style": "BW Memories"}, time=1.30)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_effect_chain_applies_in_order(frame):
    result = apply_effects(
        frame,
        [
            {"id": "color_filter", "params": {"style": "Cold Blue"}},
            {"id": "film_burn", "params": {"intensity": 0.4}},
        ],
        time=0.2,
    )
    assert result.shape == frame.shape
    assert result.dtype == np.uint8


def test_unknown_effect_raises(frame):
    with pytest.raises(KeyError):
        apply_effect(frame, "does_not_exist")
