"""Composed Tk desktop application.

Every feature lives in a small mixin module under :mod:`videomerger.gui`.
``VideoMergerStudio`` only assembles them and provides the process entry point.
"""
from __future__ import annotations

import tkinter as tk

from .audio import AudioMixin
from .audio_render import AudioRenderMixin
from .constants import GuiConstants
from .core import CoreMixin
from .effects_canopy import EffectsCanopyMixin
from .effects_film import EffectsFilmMixin
from .effects_filters import EffectsFiltersMixin
from .effects_flare import EffectsFlareMixin
from .effects_gold import EffectsGoldMixin
from .effects_motion import EffectsMotionMixin
from .effects_settings import EffectsSettingsMixin
from .effects_text3d import EffectsText3DMixin
from .effects_thug import EffectsThugMixin
from .effects_ui import EffectsUIMixin
from .export import ExportMixin
from .inspector import InspectorMixin
from .masks import MasksMixin
from .media import MediaMixin
from .playback import PlaybackMixin
from .preview import PreviewMixin
from .shell import ShellMixin
from .text3d_ui import Text3DUIMixin
from .timeline import TimelineMixin
from .timeline_drag import TimelineDragMixin
from .timeline_render import TimelineRenderMixin
from .title_cards import TitleCardsMixin
from .titles import TitlesMixin
from .tracking_impl import TrackingImplMixin
from .tracking_ui import TrackingUIMixin
from .transitions import TransitionsMixin
from .vision import VisionMixin


class VideoMergerStudio(
    CoreMixin,
    ShellMixin,
    MediaMixin,
    AudioMixin,
    AudioRenderMixin,
    PlaybackMixin,
    PreviewMixin,
    TransitionsMixin,
    InspectorMixin,
    EffectsUIMixin,
    EffectsSettingsMixin,
    TrackingUIMixin,
    Text3DUIMixin,
    TimelineMixin,
    TimelineDragMixin,
    TimelineRenderMixin,
    VisionMixin,
    TrackingImplMixin,
    MasksMixin,
    EffectsFiltersMixin,
    EffectsGoldMixin,
    EffectsFilmMixin,
    EffectsFlareMixin,
    EffectsCanopyMixin,
    EffectsText3DMixin,
    EffectsMotionMixin,
    EffectsThugMixin,
    TitlesMixin,
    TitleCardsMixin,
    ExportMixin,
    GuiConstants,
):
    """Ultimate NLE Studio Pro desktop editor."""


def main() -> None:
    """Create the Tk root, build the editor and enter the event loop."""
    root = tk.Tk()
    app = VideoMergerStudio(root)  # noqa: F841 - keeps the controller alive
    root.mainloop()


if __name__ == "__main__":
    main()
