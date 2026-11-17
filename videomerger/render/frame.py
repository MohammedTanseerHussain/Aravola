"""Single-frame preview renderer.

This is the headless equivalent of the desktop preview canvas: it resolves the
active clip, reads/creates its base frame, applies transforms, colour filters,
effects and text, and returns a PIL image.  It is intentionally independent of
MoviePy so previews are fast and easy to serve over HTTP.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from ..effects import apply_effect
from ..media import VideoFrameReader, fit_image, read_frame
from ..models import Clip, Project
from ..titles import overlay_plain_text, render_lower_third, render_title_card
from ..vision import detect_faces, detect_persons, person_mask

_EPS = 1e-6


def _effect_items(clip: Clip) -> list[tuple[str, dict[str, Any]]]:
    """Normalise explicit effects and legacy GUI flags into ``(id, params)``."""
    items: list[tuple[str, dict[str, Any]]] = []

    raw = clip.effects or {}
    if isinstance(raw, dict):
        for effect_id, params in raw.items():
            if isinstance(params, dict):
                if params.get("enabled", True):
                    items.append((effect_id, params))
            elif params:
                items.append((effect_id, {}))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("id"):
                items.append((item["id"], item.get("params") or {}))

    extra = clip.extra or {}

    # Colour filter
    if extra.get("filter_enabled") and not any(eid == "color_filter" for eid, _ in items):
        items.append(("color_filter", {
            "style": extra.get("filter_style", "Cinematic Warm"),
            "intensity": float(extra.get("filter_intensity", 1.0)),
            "warmth": float(extra.get("filter_warmth", 0.5)),
            "saturation": float(extra.get("filter_saturation", 1.0)),
            "fade_blacks": float(extra.get("filter_fade_blacks", 0.15)),
        }))

    # Legacy colour filter may also be nested in clip.filter.
    if isinstance(clip.filter, dict) and clip.filter.get("enabled", True):
        if not any(eid == "color_filter" for eid, _ in items):
            params = dict(clip.filter)
            params.pop("enabled", None)
            items.append(("color_filter", params))

    if extra.get("effect_film_burn_enabled") and not any(eid == "film_burn" for eid, _ in items):
        items.append(("film_burn", {
            "intensity": float(extra.get("film_burn_intensity", 1.0)),
            "speed": float(extra.get("film_burn_speed", 1.0)),
        }))
    if extra.get("effect_sun_glare_enabled") and not any(eid == "sun_glare" for eid, _ in items):
        items.append(("sun_glare", {
            "variation": extra.get("sun_glare_variation", "Cinematic"),
            "position": extra.get("sun_glare_position", "Top Left"),
            "intensity": float(extra.get("sun_glare_intensity", 1.0)),
            "size": float(extra.get("sun_glare_size", 1.0)),
            "speed": float(extra.get("sun_glare_speed", 0.3)),
        }))
    if extra.get("effect_x_flare_enabled") and not any(eid == "x_flare" for eid, _ in items):
        items.append(("x_flare", {
            "variation": extra.get("x_flare_variation", "Blue White"),
            "position": extra.get("x_flare_position", "Center"),
            "intensity": float(extra.get("x_flare_intensity", 1.0)),
            "size": float(extra.get("x_flare_size", 1.0)),
            "speed": float(extra.get("x_flare_speed", 0.3)),
        }))
    if extra.get("effect_light_flash_enabled") and not any(eid == "light_flash" for eid, _ in items):
        items.append(("light_flash", {
            "variation": extra.get("light_flash_variation", "White Flash"),
            "position": extra.get("light_flash_position", "Center"),
            "intensity": float(extra.get("light_flash_intensity", 1.0)),
            "size": float(extra.get("light_flash_size", 1.0)),
            "speed": float(extra.get("light_flash_speed", 1.0)),
            "density": int(extra.get("light_flash_density", 6)),
        }))
    if extra.get("effect_canopy_enabled") and not any(eid == "canopy" for eid, _ in items):
        items.append(("canopy", {
            "light_dir": extra.get("canopy_light_dir", "Top Left"),
            "light_style": extra.get("canopy_light_style", "Soft Atmosphere"),
            "fog_density": float(extra.get("canopy_fog_density", 0.7)),
            "fog_height": float(extra.get("canopy_fog_height", 0.5)),
            "ray_intensity": float(extra.get("canopy_ray_intensity", 1.0)),
            "ray_width": float(extra.get("canopy_ray_width", 1.0)),
            "warmth": float(extra.get("canopy_warmth", 0.7)),
            "shimmer": float(extra.get("canopy_shimmer", 0.3)),
            "show_light_source": bool(extra.get("canopy_show_light_source", True)),
        }))
    if extra.get("_kb_enabled") and not any(eid == "ken_burns" for eid, _ in items):
        items.append(("ken_burns", {
            "zoom_start": float(extra.get("_kb_zoom_in", 1.0)),
            "zoom_end": float(extra.get("_kb_zoom_out", 1.3)),
            "pan_x": float(extra.get("_kb_pan_x", 0.0)),
            "pan_y": float(extra.get("_kb_pan_y", 0.0)),
            "duration": clip.effective_duration(),
        }))
    if extra.get("_3d_text_enabled") and not any(eid == "three_d_text" for eid, _ in items):
        items.append(("three_d_text", {
            "text": extra.get("_3d_text_content", "TRACKING"),
            "color": extra.get("_3d_text_color", "Orange"),
            "depth": float(extra.get("_3d_text_depth", 0.4)),
            "shadow": float(extra.get("_3d_text_shadow", 0.5)),
            "style": extra.get("_3d_text_style", "Solid Matte"),
            "duration": clip.effective_duration(),
            "camera_speed": float(extra.get("_3d_cam_speed", 0.0)),
            "fade": float(extra.get("_3d_text_fade", 0.3)),
            "quad": extra.get("_3d_text_quad"),
        }))
    if extra.get("effect_thug_life_enabled") and not any(eid == "thug_life" for eid, _ in items):
        items.append(("thug_life", {
            "style": extra.get("thug_style", "realistic"),
            "entry": extra.get("thug_entry", "top"),
            "cap_enabled": bool(extra.get("thug_cap_enabled", True)),
            "glasses_override": extra.get("thug_glasses_override"),
            "chain_override": extra.get("thug_chain_override"),
            "cap_override": extra.get("thug_cap_override"),
        }))
    if extra.get("effect", "none") == "gold_outline" or extra.get("effect_global_enabled"):
        if not any(eid == "gold_outline" for eid, _ in items):
            items.append(("gold_outline", {
                "variation": extra.get("effect_variation", "ethereal"),
                "color_name": extra.get("effect_color_variation", "Gold (Default)"),
                "opacity": float(extra.get("effect_opacity", 0.9)),
                "glow": float(extra.get("effect_glow", 1.0)),
            }))
    if extra.get("motion_track_enabled") and not any(eid == "motion_track" for eid, _ in items):
        items.append(("motion_track", {
            "name": extra.get("motion_track_name", ""),
            "mode": extra.get("motion_track_mode", "arrow_and_name"),
            "color": extra.get("motion_track_color", "Yellow"),
            "text_color": extra.get("motion_track_text_color", "Yellow"),
            "arrow_size": float(extra.get("motion_track_arrow_size", 1.0)),
            "arrow_length": float(extra.get("motion_track_arrow_len", 1.0)),
            "text_size": float(extra.get("motion_track_text_size", 1.0)),
            "offset_y": float(extra.get("motion_track_offset_y", 0.0)),
        }))

    return items


def _apply_transform(image: Image.Image, clip: Clip, canvas_size: tuple[int, int]) -> Image.Image:
    width, height = canvas_size
    transform = clip.transform
    if transform.rotation:
        image = image.rotate(-transform.rotation, expand=True, resample=Image.BICUBIC)
    if transform.flip_h:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
    if transform.flip_v:
        image = image.transpose(Image.FLIP_TOP_BOTTOM)

    if abs(transform.scale - 1.0) > 1e-6:
        new_w = max(1, int(round(image.width * transform.scale)))
        new_h = max(1, int(round(image.height * transform.scale)))
        image = image.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    left = (width - image.width) // 2 + int(transform.x)
    top = (height - image.height) // 2 + int(transform.y)
    if transform.opacity < 1.0:
        image = image.convert("RGBA")
        alpha = image.getchannel("A").point(lambda v: int(v * max(0.0, min(1.0, transform.opacity))))
        image.putalpha(alpha)
        canvas = canvas.convert("RGBA")
        canvas.alpha_composite(image, (left, top))
        return canvas.convert("RGB")
    canvas.paste(image, (left, top))
    return canvas


def _placeholder(width: int, height: int, text: str = "PLACEHOLDER") -> Image.Image:
    image = Image.new("RGB", (width, height), (18, 18, 22))
    draw = ImageDraw.Draw(image)
    from ..titles import _font

    font = _font(max(14, int(height * 0.06)))
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (box[2] - box[0])) / 2, height / 2 - (box[3] - box[1]) / 2),
              text, font=font, fill=(230, 140, 30))
    return image


def _build_context(clip: Clip, frame: np.ndarray, effects: list[tuple[str, dict]]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    ids = {effect_id for effect_id, _ in effects}
    if "gold_outline" in ids:
        context["mask"] = person_mask(frame)
    if "thug_life" in ids:
        faces = detect_faces(frame)
        if faces:
            context["face"] = max(faces, key=lambda box: box[2] * box[3])
    if "motion_track" in ids:
        people = detect_persons(frame)
        if people:
            person = max(people, key=lambda p: p.bbox[2] * p.bbox[3])
            context["bbox"] = person.bbox
            context["center"] = person.center
    return context


def apply_clip_look(
    image: Image.Image,
    clip: Clip,
    local_time: float,
    width: int,
    height: int,
    *,
    smart_fill: bool = True,
) -> Image.Image:
    """Fit, transform, effect and caption one already-decoded image.

    Shared by the single-frame preview (:func:`render_clip_frame`) and the
    MoviePy exporter so both look identical.
    """
    image = fit_image(image, width, height, smart_fill=smart_fill)
    image = _apply_transform(image, clip, (width, height))

    effects = _effect_items(clip)
    if effects:
        frame = np.array(image)
        context = _build_context(clip, frame, effects)
        for effect_id, params in effects:
            params = dict(params)
            params.setdefault("duration", clip.effective_duration())
            frame = apply_effect(frame, effect_id, params, time=local_time, context=context)
        image = Image.fromarray(frame)

    # Legacy clip text caption.
    if clip.text and clip.text_start <= local_time <= clip.text_end:
        image = Image.fromarray(overlay_plain_text(np.array(image), clip.text))

    # Title-card lower third (legacy "lt_style").
    style = clip.title.get("lt_style")
    if style and clip.text and clip.text_start <= local_time <= clip.text_end:
        duration = max(0.1, clip.text_end - clip.text_start)
        overlay = render_lower_third(clip.text, width, height, style,
                                     time=local_time - clip.text_start, duration=duration)
        base = image.convert("RGBA")
        base.alpha_composite(overlay)
        image = base.convert("RGB")

    return image


def render_clip_frame(
    clip: Clip,
    local_time: float,
    width: int,
    height: int,
    *,
    smart_fill: bool = True,
    readers: dict[str, VideoFrameReader] | None = None,
) -> Image.Image:
    """Render one clip at ``local_time`` (seconds from its timeline start)."""
    kind = clip.kind
    if kind == "video" and clip.path:
        reader = None
        if readers is not None:
            reader = readers.get(clip.path)
            if reader is None:
                reader = VideoFrameReader(clip.path)
                readers[clip.path] = reader
        source_time = clip.trim_start + max(0.0, local_time) * clip.speed
        frame = reader.read(source_time) if reader is not None else read_frame(clip.path, source_time)
        image = Image.fromarray(frame)
    elif kind == "image" and clip.path:
        image = Image.fromarray(read_frame(clip.path, 0.0))
    elif kind == "title":
        main_text = clip.title.get("main_text") or clip.name or "TITLE"
        sub_text = clip.title.get("sub_text", "")
        theme = clip.title.get("theme", "Cinematic – Deep Space Stars")
        frame = render_title_card(width, height, main_text, sub_text, theme,
                                  time=local_time, duration=clip.effective_duration())
        image = Image.fromarray(frame)
    else:
        image = _placeholder(width, height, clip.text or clip.name or "PLACEHOLDER")

    return apply_clip_look(image, clip, local_time, width, height, smart_fill=smart_fill)


class FrameRenderer:
    """Reusable preview renderer that keeps video readers open."""

    def __init__(self, project: Project, *, smart_fill: bool | None = None):
        self.project = project
        self.smart_fill = project.smart_fill if smart_fill is None else smart_fill
        self.readers: dict[str, VideoFrameReader] = {}

    def render(self, time: float) -> Image.Image:
        width, height = self.project.width, self.project.height
        time = max(0.0, float(time))
        active = self.project.active_clips(time)
        if not active:
            return Image.new("RGB", (width, height), (0, 0, 0))

        current = active[-1]
        local_time = max(0.0, time - current.timeline_start)
        image = render_clip_frame(current, local_time, width, height,
                                  smart_fill=self.smart_fill, readers=self.readers)

        # Transition into the current clip.  With back-to-back clips this is a
        # fade-from-black, matching the exporter's ``crossfadein`` behaviour.
        is_first = bool(self.project.clips) and self.project.clips[0].id == current.id
        if not is_first and current.transition.lower() != "hard cut":
            elapsed = max(0.0, time - current.timeline_start)
            duration = min(float(current.transition_duration or 0.0),
                           current.effective_duration() * 0.5)
            if duration > 0 and elapsed < duration:
                progress = max(0.0, min(1.0, elapsed / duration))
                if len(active) >= 2:
                    previous = active[-2]
                    prev_local = max(0.0, time - previous.timeline_start)
                    prev_image = render_clip_frame(previous, prev_local, width, height,
                                                   smart_fill=self.smart_fill, readers=self.readers)
                    image = Image.blend(prev_image.convert("RGB"), image.convert("RGB"), progress)
                else:
                    black = Image.new("RGB", (width, height), (0, 0, 0))
                    image = Image.blend(black, image.convert("RGB"), progress)
        return image

    def close(self) -> None:
        for reader in self.readers.values():
            reader.close()
        self.readers.clear()

    def __enter__(self) -> "FrameRenderer":
        return self

    def __exit__(self, *args) -> None:
        self.close()
