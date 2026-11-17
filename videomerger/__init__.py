"""VideoMerger backend.

Small, independently callable feature libraries that sit behind both the
desktop GUI and the HTTP API.  Import only what you need; heavy dependencies
(MoviePy, MediaPipe, YOLO) are loaded lazily by the modules that use them.
"""
from __future__ import annotations

__version__ = "2.0.0"

from .audio import build_audio_mix, detect_silence, mix_audio
from .config import ACCESSORIES, MODELS, OUTPUT, ROOT, UPLOADS
from .effects import EFFECTS, apply_effect, apply_effects, list_effects
from .media import filmstrip, probe, read_frame, thumbnail, waveform_samples
from .models import AudioTrack, Clip, Project, Transform
from .render import (
    ExportCancelled,
    FrameRenderer,
    apply_clip_look,
    export_project,
    prepare_project,
    render_clip_frame,
    render_preview,
)
from .titles import composite_lower_third, overlay_plain_text, render_lower_third, render_title_card

__all__ = [
    "__version__",
    "ACCESSORIES",
    "AudioTrack",
    "Clip",
    "EFFECTS",
    "ExportCancelled",
    "FrameRenderer",
    "MODELS",
    "OUTPUT",
    "Project",
    "ROOT",
    "Transform",
    "UPLOADS",
    "apply_clip_look",
    "apply_effect",
    "apply_effects",
    "build_audio_mix",
    "composite_lower_third",
    "detect_silence",
    "export_project",
    "filmstrip",
    "list_effects",
    "mix_audio",
    "overlay_plain_text",
    "prepare_project",
    "probe",
    "read_frame",
    "render_clip_frame",
    "render_lower_third",
    "render_preview",
    "render_title_card",
    "thumbnail",
    "waveform_samples",
]
