"""Frame effects exposed individually and through one registry.

Each effect is a pure function ``frame (H,W,3 uint8) -> frame``.  Time-based
effects accept a ``time`` argument.  The API layer simply looks the effect up
in :data:`EFFECTS` and calls it.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from .canopy import apply_canopy
from .color import apply_color_filter
from .film_burn import apply_film_burn
from .gold_outline import apply_gold_outline
from .ken_burns import apply_kenburns
from .light_flash import apply_light_flash
from .motion_track import apply_motion_track
from .sun_glare import apply_sun_glare
from .three_d_text import apply_3d_text
from .thug_life import apply_thug_life
from .x_flare import apply_x_flare

EffectFn = Callable[..., np.ndarray]


def _param(name: str, type_: str, default: Any, **extra: Any) -> dict[str, Any]:
    return {"name": name, "type": type_, "default": default, **extra}


def _color(frame: np.ndarray, params: dict[str, Any], time: float = 0.0, context: dict[str, Any] | None = None) -> np.ndarray:
    return apply_color_filter(
        frame,
        style=params.get("style", "Cinematic Warm"),
        intensity=float(params.get("intensity", 1.0)),
        warmth=float(params.get("warmth", 0.5)),
        saturation=float(params.get("saturation", 1.0)),
        fade_blacks=float(params.get("fade_blacks", 0.15)),
        time=time,
    )


def _film_burn(frame: np.ndarray, params: dict[str, Any], time: float = 0.0, context: dict[str, Any] | None = None) -> np.ndarray:
    return apply_film_burn(
        frame,
        intensity=float(params.get("intensity", 1.0)),
        speed=float(params.get("speed", 1.0)),
        time=time,
    )


def _sun_glare(frame: np.ndarray, params: dict[str, Any], time: float = 0.0, context: dict[str, Any] | None = None) -> np.ndarray:
    return apply_sun_glare(
        frame,
        variation=params.get("variation", "Cinematic"),
        position=params.get("position", "Top Left"),
        intensity=float(params.get("intensity", 1.0)),
        size=float(params.get("size", 1.0)),
        speed=float(params.get("speed", 0.3)),
        time=time,
    )


def _x_flare(frame: np.ndarray, params: dict[str, Any], time: float = 0.0, context: dict[str, Any] | None = None) -> np.ndarray:
    return apply_x_flare(
        frame,
        variation=params.get("variation", "Blue White"),
        position=params.get("position", "Center"),
        intensity=float(params.get("intensity", 1.0)),
        size=float(params.get("size", 1.0)),
        speed=float(params.get("speed", 0.3)),
        time=time,
    )


def _light_flash(frame: np.ndarray, params: dict[str, Any], time: float = 0.0, context: dict[str, Any] | None = None) -> np.ndarray:
    return apply_light_flash(
        frame,
        variation=params.get("variation", "White Flash"),
        position=params.get("position", "Center"),
        intensity=float(params.get("intensity", 1.0)),
        size=float(params.get("size", 1.0)),
        speed=float(params.get("speed", 1.0)),
        density=int(params.get("density", 6)),
        time=time,
    )


def _canopy(frame: np.ndarray, params: dict[str, Any], time: float = 0.0, context: dict[str, Any] | None = None) -> np.ndarray:
    return apply_canopy(
        frame,
        light_dir=params.get("light_dir", "Top Left"),
        light_style=params.get("light_style", "Soft Atmosphere"),
        fog_density=float(params.get("fog_density", 0.7)),
        fog_height=float(params.get("fog_height", 0.5)),
        ray_intensity=float(params.get("ray_intensity", 1.0)),
        ray_width=float(params.get("ray_width", 1.0)),
        warmth=float(params.get("warmth", 0.7)),
        shimmer=float(params.get("shimmer", 0.3)),
        time=time,
        person_mask=params.get("person_mask"),
        show_light_source=bool(params.get("show_light_source", True)),
    )


def _ken_burns(frame: np.ndarray, params: dict[str, Any], time: float = 0.0, context: dict[str, Any] | None = None) -> np.ndarray:
    duration = max(1e-6, float(params.get("duration", 5.0)))
    progress = max(0.0, min(1.0, float(time) / duration))
    zoom_start = float(params.get("zoom_start", 1.0))
    zoom_end = float(params.get("zoom_end", 1.3))
    zoom = zoom_start + (zoom_end - zoom_start) * progress
    return apply_kenburns(
        frame,
        zoom=zoom,
        pan_x=float(params.get("pan_x", 0.0)),
        pan_y=float(params.get("pan_y", 0.0)),
        t_prog=progress,
        target_w=frame.shape[1],
        target_h=frame.shape[0],
    )


def _gold_outline(frame: np.ndarray, params: dict[str, Any], time: float = 0.0, context: dict[str, Any] | None = None) -> np.ndarray:
    mask = (context or {}).get("mask")
    if mask is None:
        from ..vision import person_mask

        mask = person_mask(frame, point=params.get("point"), index=int(params.get("person_index", 0)))
    if mask is None:
        return frame
    return apply_gold_outline(
        frame,
        mask,
        variation=params.get("variation", "ethereal"),
        color_name=params.get("color_name", "Gold (Default)"),
        opacity=float(params.get("opacity", 0.9)),
        glow=float(params.get("glow", 1.0)),
        time=time,
    )


def _thug_life(frame: np.ndarray, params: dict[str, Any], time: float = 0.0, context: dict[str, Any] | None = None) -> np.ndarray:
    return apply_thug_life(
        frame,
        face=(context or {}).get("face"),
        style=params.get("style", "realistic"),
        entry=params.get("entry", "top"),
        cap_enabled=bool(params.get("cap_enabled", True)),
        time=time,
        glasses_override=params.get("glasses_override"),
        chain_override=params.get("chain_override"),
        cap_override=params.get("cap_override"),
    )


def _three_d_text(frame: np.ndarray, params: dict[str, Any], time: float = 0.0, context: dict[str, Any] | None = None) -> np.ndarray:
    return apply_3d_text(
        frame,
        text=params.get("text", "TRACKING"),
        color=params.get("color", "Orange"),
        depth=float(params.get("depth", 0.4)),
        shadow=float(params.get("shadow", 0.5)),
        style=params.get("style", "Solid Matte"),
        quad=params.get("quad"),
        time=time,
        duration=float(params.get("duration", 3.0)),
        camera_speed=float(params.get("camera_speed", 0.0)),
        fade=float(params.get("fade", 0.3)),
    )


def _motion_track(frame: np.ndarray, params: dict[str, Any], time: float = 0.0, context: dict[str, Any] | None = None) -> np.ndarray:
    ctx = context or {}
    return apply_motion_track(
        frame,
        center=params.get("center") or ctx.get("center"),
        bbox=params.get("bbox") or ctx.get("bbox"),
        name=params.get("name", ""),
        mode=params.get("mode", "arrow_and_name"),
        color=params.get("color", "Yellow"),
        text_color=params.get("text_color", "Yellow"),
        arrow_size=float(params.get("arrow_size", 1.0)),
        arrow_length=float(params.get("arrow_length", 1.0)),
        text_size=float(params.get("text_size", 1.0)),
        offset_y=float(params.get("offset_y", 0.0)),
        time=time,
        track_id=params.get("track_id"),
    )


EFFECTS: dict[str, dict[str, Any]] = {
    "color_filter": {
        "label": "Color grading",
        "category": "color",
        "fn": _color,
        "animated": False,
        "params": [
            _param("style", "choice", "Cinematic Warm", choices=[
                "Cinematic Warm", "Golden Hour", "Vintage Film", "Vintage Cam",
                "BW Memories", "Teal & Orange", "Bleach Bypass", "Cold Blue",
                "Desaturated", "High Contrast",
            ]),
            _param("intensity", "float", 1.0, min=0.0, max=1.0, step=0.05),
            _param("warmth", "float", 0.5, min=0.0, max=1.0, step=0.05),
            _param("saturation", "float", 1.0, min=0.0, max=2.0, step=0.05),
            _param("fade_blacks", "float", 0.15, min=0.0, max=0.5, step=0.01),
        ],
    },
    "film_burn": {
        "label": "Film burn",
        "category": "light",
        "fn": _film_burn,
        "animated": True,
        "params": [
            _param("intensity", "float", 1.0, min=0.0, max=2.0, step=0.1),
            _param("speed", "float", 1.0, min=0.2, max=3.0, step=0.1),
        ],
    },
    "sun_glare": {
        "label": "Sun glare",
        "category": "light",
        "fn": _sun_glare,
        "animated": True,
        "params": [
            _param("variation", "choice", "Cinematic", choices=["Cinematic", "Golden Hour", "Natural", "Sky Burst"]),
            _param("position", "choice", "Top Left", choices=["Top Left", "Top Right", "Bottom Left", "Bottom Right", "Center"]),
            _param("intensity", "float", 1.0, min=0.1, max=2.0, step=0.1),
            _param("size", "float", 1.0, min=0.4, max=2.0, step=0.1),
            _param("speed", "float", 0.3, min=0.0, max=2.0, step=0.1),
        ],
    },
    "x_flare": {
        "label": "X flare",
        "category": "light",
        "fn": _x_flare,
        "animated": True,
        "params": [
            _param("variation", "choice", "Blue White", choices=["Blue White", "Purple Haze", "Golden Cross", "Ice White"]),
            _param("position", "choice", "Center", choices=["Top Left", "Top Right", "Bottom Left", "Bottom Right", "Center"]),
            _param("intensity", "float", 1.0, min=0.1, max=2.0, step=0.1),
            _param("size", "float", 1.0, min=0.3, max=2.0, step=0.1),
            _param("speed", "float", 0.3, min=0.0, max=2.0, step=0.1),
        ],
    },
    "light_flash": {
        "label": "Light flash",
        "category": "light",
        "fn": _light_flash,
        "animated": True,
        "params": [
            _param("variation", "choice", "White Flash", choices=["White Flash", "Warm Paparazzi", "Cool Studio", "Neon Burst", "Golden Gala"]),
            _param("position", "choice", "Center", choices=["Center", "Top Left", "Top Right", "Bottom Left", "Bottom Right", "Diagonal TL→BR", "Diagonal BL→TR", "Full Image"]),
            _param("intensity", "float", 1.0, min=0.1, max=2.0, step=0.1),
            _param("size", "float", 1.0, min=0.3, max=2.0, step=0.1),
            _param("speed", "float", 1.0, min=0.2, max=3.0, step=0.1),
            _param("density", "int", 6, min=3, max=20, step=1),
        ],
    },
    "canopy": {
        "label": "Canopy fog + rays",
        "category": "atmosphere",
        "fn": _canopy,
        "animated": True,
        "params": [
            _param("light_dir", "choice", "Top Left", choices=["Top Left", "Top Right", "Top Center", "Behind", "Side Left", "Side Right"]),
            _param("light_style", "choice", "Soft Atmosphere", choices=["Soft Atmosphere", "Forest Rays"]),
            _param("fog_density", "float", 0.7, min=0.1, max=2.0, step=0.1),
            _param("fog_height", "float", 0.5, min=0.2, max=0.9, step=0.05),
            _param("ray_intensity", "float", 1.0, min=0.0, max=3.0, step=0.1),
            _param("ray_width", "float", 1.0, min=0.3, max=2.0, step=0.1),
            _param("warmth", "float", 0.7, min=0.0, max=1.0, step=0.05),
            _param("shimmer", "float", 0.3, min=0.0, max=1.0, step=0.05),
            _param("show_light_source", "bool", True),
        ],
    },
    "ken_burns": {
        "label": "Ken Burns (zoom / pan)",
        "category": "motion",
        "fn": _ken_burns,
        "animated": True,
        "params": [
            _param("zoom_start", "float", 1.0, min=1.0, max=3.0, step=0.05),
            _param("zoom_end", "float", 1.3, min=1.0, max=3.0, step=0.05),
            _param("pan_x", "float", 0.0, min=-1.0, max=1.0, step=0.05),
            _param("pan_y", "float", 0.0, min=-1.0, max=1.0, step=0.05),
            _param("duration", "float", 5.0, min=0.1, max=600.0, step=0.1),
        ],
    },
    "gold_outline": {
        "label": "Gold outline / radiant aura",
        "category": "subject",
        "fn": _gold_outline,
        "animated": True,
        "needs_mask": True,
        "params": [
            _param("variation", "choice", "ethereal", choices=["ethereal", "neon", "spacy_game_rays", "gabriel_rays", "angel_rays"]),
            _param("color_name", "choice", "Gold (Default)", choices=[
                "Gold (Default)", "Warm Gold", "Orange", "Sunset", "Pink", "Purple",
                "Blue", "Cyan", "Green", "Neon Green", "White", "Red", "Yellow",
                "Ice", "Rose Gold", "Emerald", "Sapphire", "Amethyst", "Copper", "Silver",
            ]),
            _param("opacity", "float", 0.9, min=0.0, max=1.0, step=0.05),
            _param("glow", "float", 1.0, min=0.0, max=2.0, step=0.05),
        ],
    },
    "thug_life": {
        "label": "Thug life (glasses + chain)",
        "category": "subject",
        "fn": _thug_life,
        "animated": True,
        "needs_face": True,
        "params": [
            _param("style", "choice", "realistic", choices=["realistic", "pixel"]),
            _param("entry", "choice", "top", choices=["top", "left", "right", "bottom", "rush", "bounce"]),
            _param("cap_enabled", "bool", True),
        ],
    },
    "three_d_text": {
        "label": "3D text",
        "category": "text",
        "fn": _three_d_text,
        "animated": True,
        "params": [
            _param("text", "str", "TRACKING"),
            _param("color", "choice", "Orange", choices=["Orange", "White", "Gold", "Red", "Blue", "Cyan", "Green", "Purple", "Black"]),
            _param("depth", "float", 0.4, min=0.0, max=2.0, step=0.05),
            _param("shadow", "float", 0.5, min=0.0, max=1.0, step=0.05),
            _param("style", "choice", "Solid Matte", choices=["Solid Matte", "Metallic", "Glossy", "Glow"]),
            _param("duration", "float", 3.0, min=0.1, max=600.0, step=0.1),
            _param("camera_speed", "float", 0.0, min=0.0, max=40.0, step=0.5),
            _param("fade", "float", 0.3, min=0.0, max=2.0, step=0.05),
        ],
    },
    "motion_track": {
        "label": "Motion track arrow + name",
        "category": "subject",
        "fn": _motion_track,
        "animated": True,
        "needs_person": True,
        "params": [
            _param("name", "str", ""),
            _param("mode", "choice", "arrow_and_name", choices=["arrow_and_name", "arrow_only"]),
            _param("color", "choice", "Yellow", choices=["Yellow", "Red", "Green", "Blue", "White", "Orange", "Cyan", "Magenta", "Lime", "Gold"]),
            _param("text_color", "choice", "Yellow", choices=["Yellow", "White", "Red", "Green", "Blue", "Orange", "Cyan", "Magenta", "Lime", "Gold"]),
            _param("arrow_size", "float", 1.0, min=0.5, max=3.0, step=0.1),
            _param("arrow_length", "float", 1.0, min=0.5, max=3.0, step=0.1),
            _param("text_size", "float", 1.0, min=0.5, max=3.0, step=0.1),
            _param("offset_y", "float", 0.0, min=-200.0, max=200.0, step=5.0),
        ],
    },
}


def list_effects() -> list[dict[str, Any]]:
    """Frontend-friendly effect catalogue (no callables)."""
    return [
        {
            "id": effect_id,
            "label": spec["label"],
            "category": spec["category"],
            "animated": spec["animated"],
            "params": spec["params"],
        }
        for effect_id, spec in EFFECTS.items()
    ]


def apply_effect(
    frame: np.ndarray,
    effect_id: str,
    params: dict[str, Any] | None = None,
    *,
    time: float = 0.0,
    context: dict[str, Any] | None = None,
) -> np.ndarray:
    """Apply one named effect to an RGB frame.

    ``context`` can carry pre-computed data (``mask``, ``face``, ``center``,
    ``bbox``) when the caller already ran detection.
    """
    spec = EFFECTS.get(effect_id)
    if spec is None:
        raise KeyError(f"unknown effect: {effect_id!r}. Available: {sorted(EFFECTS)}")
    params = dict(params or {})
    return spec["fn"](frame, params, time=float(time), context=context)


def apply_effects(
    frame: np.ndarray,
    effects: list[dict[str, Any]],
    *,
    time: float = 0.0,
    context: dict[str, Any] | None = None,
) -> np.ndarray:
    """Apply a chain of ``{id, params}`` effects in order."""
    for item in effects:
        frame = apply_effect(frame, item["id"], item.get("params"), time=time, context=context)
    return frame
