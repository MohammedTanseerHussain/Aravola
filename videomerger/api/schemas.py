"""Request bodies for the HTTP API.

Pydantic is only used at the edge.  Internally everything is converted to the
plain dictionaries consumed by :mod:`videomerger.models`.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProjectPayload(_Base):
    id: str | None = None
    name: str | None = None
    format: str | None = None
    width: int | None = None
    height: int | None = None
    fps: int | None = None
    smart_fill: bool | None = None
    auto_rotate: bool | None = None
    clips: list[dict[str, Any]] = Field(default_factory=list)
    audio_tracks: list[dict[str, Any]] = Field(default_factory=list)


class ProjectPatch(_Base):
    name: str | None = None
    format: str | None = None
    width: int | None = None
    height: int | None = None
    fps: int | None = None
    smart_fill: bool | None = None
    auto_rotate: bool | None = None


class ClipPayload(_Base):
    id: str | None = None
    kind: str | None = None
    path: str | None = None
    name: str | None = None
    duration: float | None = None
    source_duration: float | None = None
    timeline_start: float | None = None
    trim_start: float | None = None
    trim_end: float | None = None
    speed: float | None = None
    volume: float | None = None
    muted: bool | None = None
    transform: dict[str, Any] | None = None
    transition: str | None = None
    transition_duration: float | None = None
    text: str | None = None
    text_start: float | None = None
    text_end: float | None = None
    title: dict[str, Any] | None = None
    filter: dict[str, Any] | None = None
    effects: dict[str, dict[str, Any]] | None = None
    extra: dict[str, Any] | None = None


class AddClipRequest(_Base):
    clip: dict[str, Any]
    index: int | None = None
    probe: bool = True


class ClipPatch(_Base):
    kind: str | None = None
    path: str | None = None
    name: str | None = None
    duration: float | None = None
    source_duration: float | None = None
    timeline_start: float | None = None
    trim_start: float | None = None
    trim_end: float | None = None
    speed: float | None = None
    volume: float | None = None
    muted: bool | None = None
    transform: dict[str, Any] | None = None
    transition: str | None = None
    transition_duration: float | None = None
    text: str | None = None
    text_start: float | None = None
    text_end: float | None = None
    title: dict[str, Any] | None = None
    filter: dict[str, Any] | None = None
    effects: dict[str, dict[str, Any]] | None = None
    extra: dict[str, Any] | None = None


class SplitRequest(_Base):
    time: float


class MoveRequest(_Base):
    clip_id: str
    index: int


class ReflowRequest(_Base):
    start: float = 0.0


class AudioPayload(_Base):
    id: str | None = None
    path: str | None = None
    name: str | None = None
    volume: float | None = None
    start_offset: float | None = None
    trim_start: float | None = None
    trim_end: float | None = None
    speed: float | None = None
    muted: bool | None = None
    source_duration: float | None = None
    envelope: list[list[float]] | None = None
    mute_regions: list[list[float]] | None = None
    pt_gains: dict[str, float] | None = None
    ease_mode: str | None = None
    extra: dict[str, Any] | None = None


class AddAudioRequest(_Base):
    audio: dict[str, Any]
    index: int | None = None
    probe: bool = True


class EffectSlotRequest(_Base):
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class EffectApplyRequest(_Base):
    path: str | None = None
    image_base64: str | None = None
    time: float = 0.0
    params: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class PreviewRequest(_Base):
    time: float = 0.0
    width: int | None = None
    height: int | None = None


class ExportRequest(_Base):
    output_name: str | None = None
    fps: int | None = None
    codec: str = "libx264"
    audio_codec: str = "aac"
    preset: str = "ultrafast"
    threads: int | None = None


class TitleRequest(_Base):
    main_text: str = "TITLE"
    sub_text: str = ""
    theme: str = "Cinematic – Deep Space Stars"
    width: int = 1920
    height: int = 1080
    time: float = 0.0
    duration: float = 5.0


class LowerThirdRequest(_Base):
    text: str = "Lower third"
    style: str = "Static Aurora Tile (Bracket)"
    width: int = 1920
    height: int = 1080
    time: float = 0.0
    duration: float = 3.0


class VisionRequest(_Base):
    path: str | None = None
    image_base64: str | None = None
    time: float = 0.0
    confidence: float = 0.25
    point: list[int] | None = None
    index: int = 0


class AudioMixRequest(_Base):
    project_id: str | None = None
    project: dict[str, Any] | None = None
    filename: str = "mix.wav"


class SilenceRequest(_Base):
    path: str
    threshold_db: float = -35.0
    min_silence: float = 0.25
    samples: int = 600


class ProbeRequest(_Base):
    path: str
