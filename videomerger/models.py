"""Serialisable project model shared by the API, renderer and tests.

The desktop application stores clips as loose dictionaries.  This module gives
the backend a small, typed layer while keeping a compatibility path
(:meth:`Clip.from_legacy_dict`) for projects created by the old GUI.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .config import OUTPUT_FPS

LANDSCAPE = (1920, 1080)
PORTRAIT = (1080, 1920)


def _new_id(prefix: str = "clip") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class Transform:
    """Visual transform applied after the source frame has been fitted."""

    scale: float = 1.0
    opacity: float = 1.0
    x: int = 0
    y: int = 0
    rotation: int = 0  # degrees, clockwise
    flip_h: bool = False
    flip_v: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Transform":
        data = data or {}
        return cls(
            scale=float(data.get("scale", 1.0)),
            opacity=float(data.get("opacity", 1.0)),
            x=int(data.get("x", data.get("x_offset", 0)) or 0),
            y=int(data.get("y", data.get("y_offset", 0)) or 0),
            rotation=int(data.get("rotation", 0) or 0),
            flip_h=bool(data.get("flip_h", False)),
            flip_v=bool(data.get("flip_v", False)),
        )


@dataclass
class Clip:
    """One item on the video track."""

    id: str = field(default_factory=_new_id)
    kind: str = "video"  # video | image | title | placeholder
    path: str = ""
    name: str = ""
    duration: float = 5.0
    source_duration: float | None = None
    timeline_start: float = 0.0
    trim_start: float = 0.0
    trim_end: float | None = None
    speed: float = 1.0
    volume: float = 1.0
    muted: bool = False
    transform: Transform = field(default_factory=Transform)
    transition: str = "Crossfade"
    transition_duration: float = 0.75
    text: str = ""
    text_start: float = 0.0
    text_end: float = 3.0
    title: dict[str, Any] = field(default_factory=dict)
    filter: dict[str, Any] | None = None
    effects: dict[str, dict[str, Any]] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # duration helpers
    # ------------------------------------------------------------------
    @property
    def is_video(self) -> bool:
        return self.kind == "video"

    @property
    def is_visual(self) -> bool:
        return self.kind in {"video", "image", "title", "placeholder"}

    def effective_duration(self) -> float:
        """Duration occupied on the timeline, taking trim and speed into account."""
        if self.is_video and self.path:
            src = float(self.source_duration or self.duration or 0.0)
            if src <= 0:
                src = float(self.trim_end or 0.0) or 5.0
            end = float(self.trim_end) if self.trim_end else src
            end = min(end, src) if src > 0 else end
            start = max(0.0, float(self.trim_start))
            return max(0.01, (end - start) / max(0.01, float(self.speed)))
        return max(0.01, float(self.duration) / max(0.01, float(self.speed)))

    @property
    def timeline_end(self) -> float:
        return float(self.timeline_start) + self.effective_duration()

    def local_time(self, absolute_time: float) -> float:
        """Convert timeline time to source time (before speed adjustment)."""
        elapsed = max(0.0, absolute_time - float(self.timeline_start))
        return float(self.trim_start) + elapsed * float(self.speed)

    def contains(self, absolute_time: float) -> bool:
        return self.timeline_start <= absolute_time < self.timeline_end

    # ------------------------------------------------------------------
    # serialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["transform"] = asdict(self.transform)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Clip":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        extra = {k: copy.deepcopy(v) for k, v in data.items() if k not in known}
        transform = Transform.from_dict(data.get("transform") or data)
        clip = cls(
            id=str(data.get("id") or _new_id()),
            kind=str(data.get("kind") or data.get("type") or "video"),
            path=str(data.get("path") or ""),
            name=str(data.get("name") or ""),
            duration=float(data.get("duration", 5.0) or 5.0),
            source_duration=(
                float(data["source_duration"])
                if data.get("source_duration") is not None
                else None
            ),
            timeline_start=float(data.get("timeline_start", data.get("tl_start", 0.0)) or 0.0),
            trim_start=float(data.get("trim_start", data.get("clip_start", 0.0)) or 0.0),
            trim_end=(
                float(data["trim_end"])
                if data.get("trim_end") is not None
                else (
                    float(data["clip_end"])
                    if data.get("clip_end") not in (None, 0, 0.0)
                    else None
                )
            ),
            speed=float(data.get("speed", 1.0) or 1.0),
            volume=float(data.get("volume", 1.0) or 1.0),
            muted=bool(data.get("muted", False)),
            transform=transform,
            transition=str(data.get("transition") or data.get("trans") or "Crossfade"),
            transition_duration=float(data.get("transition_duration", 0.75) or 0.75),
            text=str(data.get("text") or ""),
            text_start=float(data.get("text_start", 0.0) or 0.0),
            text_end=float(data.get("text_end", 3.0) or 3.0),
            title=copy.deepcopy(data.get("title") or {}),
            filter=copy.deepcopy(data.get("filter")),
            effects=copy.deepcopy(data.get("effects") or {}),
            extra=extra,
        )
        # Legacy GUI title-card fields live at the top level.
        for key in ("main_text", "sub_text", "theme", "lt_style"):
            if key in data and key not in clip.title:
                clip.title[key] = data[key]
        return clip

    @classmethod
    def from_legacy_dict(cls, data: dict[str, Any]) -> "Clip":
        return cls.from_dict(data)


@dataclass
class AudioTrack:
    """Background-music / voice-over track."""

    id: str = field(default_factory=lambda: _new_id("audio"))
    path: str = ""
    name: str = ""
    volume: float = 1.0
    start_offset: float = 0.0
    trim_start: float = 0.0
    trim_end: float | None = None
    speed: float = 1.0
    muted: bool = False
    source_duration: float | None = None
    # Envelope points are (fraction_of_track_duration, gain).  A value of 1.0
    # is the original volume; values above 1.0 boost.
    envelope: list[list[float]] = field(default_factory=list)
    mute_regions: list[list[float]] = field(default_factory=list)  # absolute seconds
    pt_gains: dict[str, float] = field(default_factory=dict)
    ease_mode: str = "none"
    extra: dict[str, Any] = field(default_factory=dict)

    def effective_duration(self) -> float:
        src = float(self.source_duration or 0.0)
        if src <= 0:
            src = float(self.trim_end or 0.0) or 10.0
        end = float(self.trim_end) if self.trim_end else src
        end = min(end, src) if src > 0 else end
        start = max(0.0, float(self.trim_start))
        return max(0.01, (end - start) / max(0.01, float(self.speed)))

    @property
    def timeline_end(self) -> float:
        return float(self.start_offset) + self.effective_duration()

    def contains(self, time: float) -> bool:
        return self.start_offset <= time < self.timeline_end

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AudioTrack":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        extra = {k: copy.deepcopy(v) for k, v in data.items() if k not in known}
        return cls(
            id=str(data.get("id") or _new_id("audio")),
            path=str(data.get("path") or ""),
            name=str(data.get("name") or ""),
            volume=float(data.get("volume", 1.0) or 1.0),
            start_offset=float(data.get("start_offset", 0.0) or 0.0),
            trim_start=float(data.get("trim_start", data.get("clip_start", 0.0)) or 0.0),
            trim_end=(
                float(data["trim_end"])
                if data.get("trim_end") is not None
                else (
                    float(data["clip_end"])
                    if data.get("clip_end") not in (None, 0, 0.0)
                    else None
                )
            ),
            speed=float(data.get("speed", 1.0) or 1.0),
            muted=bool(data.get("muted", False)),
            source_duration=(
                float(data["source_duration"])
                if data.get("source_duration") is not None
                else None
            ),
            envelope=copy.deepcopy(data.get("envelope") or data.get("vol_envelope") or []),
            mute_regions=copy.deepcopy(data.get("mute_regions") or []),
            pt_gains=copy.deepcopy(data.get("pt_gains") or {}),
            ease_mode=str(data.get("ease_mode") or "none"),
            extra=extra,
        )

    @classmethod
    def from_legacy_dict(cls, data: dict[str, Any]) -> "AudioTrack":
        return cls.from_dict(data)


@dataclass
class Project:
    """A complete edit: video track, audio tracks and output settings."""

    id: str = field(default_factory=lambda: _new_id("prj"))
    name: str = "Untitled project"
    format: str = "landscape"  # landscape | portrait
    width: int = 0
    height: int = 0
    fps: int = OUTPUT_FPS
    smart_fill: bool = True
    auto_rotate: bool = True
    clips: list[Clip] = field(default_factory=list)
    audio_tracks: list[AudioTrack] = field(default_factory=list)
    version: int = 1

    def __post_init__(self) -> None:
        if not self.width or not self.height:
            self.width, self.height = PORTRAIT if self.format == "portrait" else LANDSCAPE

    # ------------------------------------------------------------------
    # lookup / timeline
    # ------------------------------------------------------------------
    def total_duration(self) -> float:
        ends = [clip.timeline_end for clip in self.clips]
        ends.extend(track.timeline_end for track in self.audio_tracks)
        return max(ends) if ends else 0.0

    def find_clip(self, clip_id: str) -> Clip | None:
        return next((clip for clip in self.clips if clip.id == clip_id), None)

    def find_audio(self, track_id: str) -> AudioTrack | None:
        return next((track for track in self.audio_tracks if track.id == track_id), None)

    def clip_at(self, time: float) -> Clip | None:
        for clip in self.clips:
            if clip.contains(time):
                return clip
        return None

    def active_clips(self, time: float) -> list[Clip]:
        """All clips visible at ``time`` (useful for transitions/overlays)."""
        return [clip for clip in self.clips if clip.contains(time)]

    # ------------------------------------------------------------------
    # editing operations
    # ------------------------------------------------------------------
    def add_clip(self, clip: Clip, index: int | None = None) -> Clip:
        if index is None:
            self.clips.append(clip)
        else:
            self.clips.insert(index, clip)
        return clip

    def add_audio(self, track: AudioTrack, index: int | None = None) -> AudioTrack:
        if index is None:
            self.audio_tracks.append(track)
        else:
            self.audio_tracks.insert(index, track)
        return track

    def remove_clip(self, clip_id: str) -> bool:
        before = len(self.clips)
        self.clips = [clip for clip in self.clips if clip.id != clip_id]
        return len(self.clips) != before

    def remove_audio(self, track_id: str) -> bool:
        before = len(self.audio_tracks)
        self.audio_tracks = [track for track in self.audio_tracks if track.id != track_id]
        return len(self.audio_tracks) != before

    def move_clip(self, clip_id: str, new_index: int) -> bool:
        clip = self.find_clip(clip_id)
        if clip is None:
            return False
        self.clips.remove(clip)
        new_index = max(0, min(int(new_index), len(self.clips)))
        self.clips.insert(new_index, clip)
        return True

    def split_clip(self, clip_id: str, at_time: float) -> tuple[Clip, Clip] | None:
        """Split a clip at an absolute timeline time.

        The source trim of the left piece is shortened and the right piece is
        placed immediately after it.  Returns ``(left, right)`` or ``None`` when
        the cut is not inside the clip.
        """
        clip = self.find_clip(clip_id)
        if clip is None:
            return None
        if not (clip.timeline_start < at_time < clip.timeline_end):
            return None

        local = at_time - clip.timeline_start
        right = copy.deepcopy(clip)
        right.id = _new_id()
        right.timeline_start = at_time

        if clip.is_video and clip.path:
            cut_source = clip.trim_start + local * clip.speed
            right.trim_start = cut_source
            clip.trim_end = cut_source
        else:
            left_dur = local
            right_dur = max(0.01, clip.effective_duration() - local)
            clip.duration = left_dur
            right.duration = right_dur

        index = self.clips.index(clip)
        self.clips.insert(index + 1, right)
        return clip, right

    def reflow(self, start: float = 0.0) -> None:
        """Lay the video track out back-to-back (the desktop GUI behaviour)."""
        cursor = start
        for clip in self.clips:
            clip.timeline_start = cursor
            cursor = clip.timeline_end

    def sort_by_timeline(self) -> None:
        self.clips.sort(key=lambda clip: (clip.timeline_start, clip.id))

    # ------------------------------------------------------------------
    # serialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "smart_fill": self.smart_fill,
            "auto_rotate": self.auto_rotate,
            "version": self.version,
            "duration": self.total_duration(),
            "clips": [clip.to_dict() for clip in self.clips],
            "audio_tracks": [track.to_dict() for track in self.audio_tracks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        clips_data = data.get("clips")
        if clips_data is None:
            clips_data = data.get("media") or data.get("media_queue") or []
        audio_data = data.get("audio_tracks")
        if audio_data is None:
            audio_data = data.get("bgm") or data.get("bgm_tracks") or []

        project = cls(
            id=str(data.get("id") or _new_id("prj")),
            name=str(data.get("name") or "Untitled project"),
            format=str(data.get("format") or "landscape"),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            fps=int(data.get("fps") or OUTPUT_FPS),
            smart_fill=bool(data.get("smart_fill", True)),
            auto_rotate=bool(data.get("auto_rotate", True)),
            clips=[Clip.from_dict(item) for item in clips_data],
            audio_tracks=[AudioTrack.from_dict(item) for item in audio_data],
            version=int(data.get("version") or 1),
        )
        return project

    def copy(self) -> "Project":
        return Project.from_dict(self.to_dict())

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------
    def validate(self, require_files: bool = False) -> list[str]:
        errors: list[str] = []
        if self.format not in {"landscape", "portrait"}:
            errors.append("format must be 'landscape' or 'portrait'")
        if self.fps <= 0:
            errors.append("fps must be positive")
        if not self.clips:
            errors.append("project has no clips")
        seen: set[str] = set()
        for clip in self.clips:
            if clip.id in seen:
                errors.append(f"duplicate clip id: {clip.id}")
            seen.add(clip.id)
            if clip.kind not in {"video", "image", "title", "placeholder"}:
                errors.append(f"{clip.id}: unsupported kind {clip.kind!r}")
            if clip.kind in {"video", "image"} and not clip.path:
                errors.append(f"{clip.id}: missing path")
            if require_files and clip.path:
                from pathlib import Path

                if not Path(clip.path).exists():
                    errors.append(f"{clip.id}: file not found: {clip.path}")
            if clip.effective_duration() <= 0:
                errors.append(f"{clip.id}: duration must be positive")
        return errors


def normalise_clips(clips: Iterable[dict[str, Any]]) -> list[Clip]:
    """Convenience helper for API payloads containing raw dictionaries."""
    return [Clip.from_dict(item) for item in clips]
