"""MoviePy export pipeline.

The exporter is deliberately thin: all per-frame look/effects/titles come from
:func:`videomerger.render.frame.apply_clip_look`, the same function used for
preview stills.  That guarantees the API preview and the final MP4 match.

Audio is mixed separately with :func:`videomerger.audio.build_audio_mix`, so
video clips are opened with ``audio=False`` (the legacy app did this too, to
avoid MoviePy's dual A/V seek failures on Windows).
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image

from ..audio import build_audio_mix
from ..media import probe
from ..models import Clip, Project
from ..titles import render_title_card
from .frame import apply_clip_look

ProgressCallback = Callable[[float], None]

_SAFE_MARGIN = 0.05


class ExportCancelled(RuntimeError):
    pass


try:  # proglog ships with MoviePy, but keep the import optional.
    from proglog import ProgressBarLogger as _ProgressBarLogger
except Exception:  # pragma: no cover - minimal MoviePy installs
    _ProgressBarLogger = object  # type: ignore[assignment,misc]


class ExportProgressLogger(_ProgressBarLogger):  # type: ignore[misc,valid-type]
    """Proglog-compatible logger that forwards progress and honours cancel."""

    def __init__(self, callback: ProgressCallback | None = None,
                 cancel_event: threading.Event | None = None):
        try:
            super().__init__()
        except TypeError:  # object.__init__ with args
            pass
        self._progress_callback = callback
        self.cancel_event = cancel_event
        self.last_progress = 0.0

    def bars_callback(self, bar, attr, value, old_value=None):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise ExportCancelled("export cancelled")
        if attr != "index" or self._progress_callback is None:
            return
        try:
            total = float(self.bars[bar].get("total") or 0.0)
        except Exception:
            total = 0.0
        if total <= 0:
            return
        progress = max(0.0, min(1.0, float(value) / total))
        if progress >= self.last_progress - 1e-4:
            self.last_progress = progress
            try:
                self._progress_callback(progress)
            except Exception:
                pass


def prepare_project(project: Project, *, probe_files: bool = True) -> list[str]:
    """Fill in source metadata required by timing calculations.

    Returns a list of non-fatal problems (missing files, unreadable media).
    """
    problems: list[str] = []
    for clip in project.clips:
        if clip.kind not in {"video", "image"} or not clip.path:
            continue
        if not Path(clip.path).exists():
            problems.append(f"{clip.id}: file not found: {clip.path}")
            continue
        if clip.kind == "video" and (clip.source_duration is None or probe_files):
            info = probe(clip.path)
            if info.error:
                problems.append(f"{clip.id}: {info.error}")
                continue
            if info.duration > 0:
                clip.source_duration = info.duration
                if clip.trim_end is None or clip.trim_end > info.duration:
                    clip.trim_end = info.duration
    for track in project.audio_tracks:
        if not track.path:
            continue
        if not Path(track.path).exists():
            problems.append(f"{track.id}: file not found: {track.path}")
            continue
        info = probe(track.path)
        if info.duration > 0:
            track.source_duration = info.duration
            if track.trim_end is None or track.trim_end > info.duration:
                track.trim_end = info.duration
        elif info.error:
            problems.append(f"{track.id}: {info.error}")
    return problems


def _center_zoom(frame: np.ndarray, zoom: float) -> np.ndarray:
    if zoom <= 1.0001:
        return frame
    h, w = frame.shape[:2]
    new_w, new_h = max(1, int(w * zoom)), max(1, int(h * zoom))
    import cv2

    scaled = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return scaled[top:top + h, left:left + w]


def _reverse_clip(clip, fps: int):
    duration = float(clip.duration or 0.0)
    return clip.fl_time(lambda t: max(0.0, duration - float(t) - 1.0 / max(1, fps)))


def _build_visual_clip(
    project: Project,
    clip: Clip,
    *,
    fps: int,
) -> tuple[Any, list[Any]]:
    """Return ``(moviepy_clip, resources_to_close)`` for one project clip."""
    from moviepy.editor import ColorClip, ImageClip, VideoClip, VideoFileClip

    width, height = project.width, project.height
    duration = clip.effective_duration()
    resources: list[Any] = []
    extra = clip.extra or {}

    def render_overlay(image: Image.Image, local_time: float) -> np.ndarray:
        return np.array(apply_clip_look(
            image, clip, local_time, width, height,
            smart_fill=project.smart_fill,
        ))

    if clip.kind == "video" and clip.path:
        source_duration = float(clip.source_duration or 0.0)
        if source_duration <= 0:
            info = probe(clip.path)
            source_duration = info.duration
            clip.source_duration = info.duration or None
        if source_duration <= 0:
            raise ValueError(f"{clip.id}: cannot determine duration of {clip.path}")

        raw = VideoFileClip(clip.path, audio=False)
        resources.append(raw)
        source_duration = float(raw.duration or source_duration)
        clip.source_duration = source_duration

        start = max(0.0, float(clip.trim_start))
        end = float(clip.trim_end) if clip.trim_end else source_duration
        end = min(end, source_duration)
        start = min(start, max(0.0, end - _SAFE_MARGIN))
        if end - start < 0.01:
            start, end = 0.0, min(source_duration, max(0.1, source_duration))
        source = raw.subclip(start, end)

        if abs(float(clip.speed) - 1.0) > 1e-6:
            from moviepy.video.fx.all import speedx

            source = source.fx(speedx, float(clip.speed))
        source = source.set_duration(duration)

        highlight = extra.get("_highlight_effect")
        if highlight == "reverse":
            source = _reverse_clip(source, fps)
        zoom = float(extra.get("_highlight_zoom", 1.0) or 1.0) if highlight == "slowmo_zoom" else 1.0

        def make_frame(get_frame, t, _source=source, _zoom=zoom):
            frame = get_frame(t)
            if _zoom > 1.0001:
                frame = _center_zoom(frame, _zoom)
            return render_overlay(Image.fromarray(frame.astype(np.uint8)), float(t))

        movie_clip = source.fl(make_frame).set_duration(duration)
        return movie_clip, resources

    if clip.kind == "image" and clip.path:
        raw = ImageClip(clip.path).set_duration(duration)
        resources.append(raw)

        def make_frame(get_frame, t):
            return render_overlay(Image.fromarray(get_frame(0).astype(np.uint8)), float(t))

        return raw.fl(make_frame).set_duration(duration), resources

    if clip.kind == "title":
        main_text = clip.title.get("main_text") or clip.name or "TITLE"
        sub_text = clip.title.get("sub_text", "")
        theme = clip.title.get("theme", "Cinematic – Deep Space Stars")

        def title_frame(t):
            base = render_title_card(width, height, main_text, sub_text, theme,
                                     time=float(t), duration=duration)
            return render_overlay(Image.fromarray(base), float(t))

        movie_clip = VideoClip(title_frame, duration=duration)
        return movie_clip, resources

    # Placeholder card.
    placeholder = Image.new("RGB", (width, height), (18, 18, 22))

    def placeholder_frame(t):
        return render_overlay(placeholder.copy(), float(t))

    movie_clip = VideoClip(placeholder_frame, duration=duration)
    return movie_clip, resources


def export_project(
    project: Project,
    output_path: str,
    *,
    fps: int | None = None,
    codec: str = "libx264",
    audio_codec: str = "aac",
    preset: str = "ultrafast",
    threads: int | None = None,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    logger: Any = "auto",
) -> str:
    """Render ``project`` to ``output_path`` and return the path."""
    from moviepy.editor import CompositeVideoClip

    if not project.clips:
        raise ValueError("project has no clips")

    fps = int(fps or project.fps or 30)
    problems = prepare_project(project)
    if any("file not found" in problem for problem in problems):
        raise FileNotFoundError("; ".join(p for p in problems if "file not found" in p))

    total = max(0.01, float(project.total_duration()))
    layers: list[Any] = []
    resources: list[Any] = []
    visual_clips: list[Any] = []
    final = None
    audio_mix = None
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        from moviepy.editor import ColorClip

        background = ColorClip(size=(project.width, project.height), color=(0, 0, 0))
        background = background.set_duration(total).set_start(0)
        layers.append(background)

        for index, clip in enumerate(project.clips):
            movie_clip, clip_resources = _build_visual_clip(project, clip, fps=fps)
            resources.extend(clip_resources)
            visual_clips.append(movie_clip)
            if index > 0 and clip.transition.lower() != "hard cut":
                fade = min(float(clip.transition_duration or 0.0),
                           max(0.0, movie_clip.duration * 0.5))
                if fade > 0:
                    movie_clip = movie_clip.crossfadein(fade)
            layers.append(movie_clip.set_start(float(clip.timeline_start)))

        final = CompositeVideoClip(layers, size=(project.width, project.height))
        final = final.set_duration(total)

        try:
            audio_mix = build_audio_mix(project)
        except Exception:
            audio_mix = None
        if audio_mix is not None:
            audio_mix = audio_mix.set_duration(total)
            final = final.set_audio(audio_mix)

        progress_logger = None
        if logger == "auto":
            progress_logger = ExportProgressLogger(progress, cancel_event)
        elif logger is not None:
            progress_logger = logger

        write_kwargs = dict(
            fps=fps,
            codec=codec,
            audio_codec=audio_codec,
            preset=preset,
            logger=progress_logger,
            remove_temp=True,
            temp_audiofile=str(output.with_name(output.stem + ".temp-audio.m4a")),
        )
        if threads is not None:
            write_kwargs["threads"] = int(threads)
        final.write_videofile(str(output), **write_kwargs)
        return str(output)
    finally:
        for resource in [audio_mix, final, *visual_clips, *resources, *layers]:
            if resource is None:
                continue
            try:
                resource.close()
            except Exception:
                pass


def render_preview(
    project: Project,
    time: float,
    output_path: str,
    *,
    width: int | None = None,
    height: int | None = None,
) -> str:
    """Write a single preview frame to ``output_path`` (image)."""
    from .frame import FrameRenderer

    renderer = FrameRenderer(project)
    try:
        image = renderer.render(float(time))
        if width or height:
            size = (width or image.width, height or image.height)
            image = image.resize(size, Image.LANCZOS)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
    finally:
        renderer.close()
    return output_path
