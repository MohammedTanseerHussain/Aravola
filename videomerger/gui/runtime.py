"""Shared runtime for the desktop GUI.

This module owns everything the feature mixins have in common:

* the standard-library and third-party imports (Tk, NumPy, OpenCV, Pillow);
* the dark-studio colour tokens and small Tk widgets;
* lazy loading for MoviePy and Pygame, including propagation of the loaded
  objects to every feature module.

Keeping the lazy objects here means the GUI still starts quickly, while a
feature module can simply use ``VideoFileClip`` or ``pygame`` after calling
``_ensure_moviepy()`` / ``_ensure_pygame()``.
"""
from __future__ import annotations

import copy
import math
import os
import sys
import threading
import time
import traceback
import warnings

import cv2
import numpy as np

# --- SILENCE ANNOYING PILLOW WARNINGS ---
warnings.filterwarnings("ignore", category=DeprecationWarning)

import PIL.Image
from PIL import ImageDraw, ImageFilter, ImageFont, ImageTk

# --- PIL ANTIALIAS FIX FOR PILLOW >= 10.0.0 ---
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from ..config import HAAR_CASCADE

# --- IMAGEMAGICK PATH ---
os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"

# --- HAAR CASCADE PATH (OpenCV 5.0 pip package ships without data files) ---
_HAAR_CASCADE_PATH = str(HAAR_CASCADE) if HAAR_CASCADE else ""
if not _HAAR_CASCADE_PATH or not os.path.isfile(_HAAR_CASCADE_PATH):
    # Fallback: try cv2.data path
    try:
        import cv2.data

        _cv2_cascade = os.path.join(
            cv2.data.haarcascades, "haarcascade_frontalface_default.xml"
        )
        if os.path.isfile(_cv2_cascade):
            _HAAR_CASCADE_PATH = _cv2_cascade
    except Exception:
        pass

# --- LAZY LOADING: moviepy & pygame imported on first use for fast startup ---
VideoFileClip = None
ImageClip = None
ColorClip = None
CompositeVideoClip = None
TextClip = None
AudioFileClip = None
CompositeAudioClip = None
VideoClip = None
concatenate_audioclips = None
AudioArrayClip = None
vfx = None
_MOVIEPY_LOADED = False

HAS_PYGAME = False
pygame = None

_LAZY_EXPORTS = (
    "_MOVIEPY_LOADED",
    "VideoFileClip",
    "ImageClip",
    "ColorClip",
    "CompositeVideoClip",
    "TextClip",
    "AudioFileClip",
    "CompositeAudioClip",
    "VideoClip",
    "concatenate_audioclips",
    "AudioArrayClip",
    "vfx",
    "HAS_PYGAME",
    "pygame",
)


def _sync_lazy_globals() -> None:
    """Copy freshly-loaded MoviePy/Pygame objects into every GUI module.

    A Python function resolves globals through the module where it was
    defined, so ``from .runtime import *`` alone would leave the feature
    modules holding the initial ``None`` values.  The lazy loaders call this
    after importing the real objects.
    """
    package_prefix = __name__.rsplit(".", 1)[0] + "."
    values = {name: globals().get(name) for name in _LAZY_EXPORTS}
    for module in list(sys.modules.values()):
        if module is None:
            continue
        module_name = getattr(module, "__name__", "")
        if module_name.startswith(package_prefix):
            module.__dict__.update(values)


def _ensure_moviepy():
    global _MOVIEPY_LOADED, VideoFileClip, ImageClip, ColorClip, CompositeVideoClip
    global TextClip, AudioFileClip, CompositeAudioClip, VideoClip
    global concatenate_audioclips, AudioArrayClip, vfx
    if _MOVIEPY_LOADED:
        return
    from moviepy.editor import (
        VideoFileClip as _VFC,
        ImageClip as _IC,
        ColorClip as _CC,
        CompositeVideoClip as _CVC,
        TextClip as _TC,
        AudioFileClip as _AFC,
        CompositeAudioClip as _CAC,
        VideoClip as _VC,
        concatenate_audioclips as _concat,
    )
    from moviepy.audio.AudioClip import AudioArrayClip as _AAC
    import moviepy.video.fx.all as _vfx

    VideoFileClip = _VFC
    ImageClip = _IC
    ColorClip = _CC
    CompositeVideoClip = _CVC
    TextClip = _TC
    AudioFileClip = _AFC
    CompositeAudioClip = _CAC
    VideoClip = _VC
    concatenate_audioclips = _concat
    AudioArrayClip = _AAC
    vfx = _vfx
    _MOVIEPY_LOADED = True
    _sync_lazy_globals()


def _ensure_pygame():
    global HAS_PYGAME, pygame
    if HAS_PYGAME:
        return
    try:
        import pygame as _pg

        _pg.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
        pygame = _pg
        HAS_PYGAME = True
    except Exception as e:
        HAS_PYGAME = False
        print(
            "WARNING: Pygame initialization failed. "
            "Live audio preview will be disabled.",
            e,
        )
    _sync_lazy_globals()


# --- LIVE EXPORT PROGRESS (hooks moviepy's proglog system back into the Tk UI) ---
try:
    from proglog import ProgressBarLogger
except Exception:
    ProgressBarLogger = None


class _TkExportProgressLogger(ProgressBarLogger if ProgressBarLogger else object):
    """Feed moviepy's ``write_videofile`` progress back to the Tk UI.

    ``on_progress(pct: int)`` is called from MoviePy's render thread, so it
    must itself hop back to the Tk main thread.
    """

    def __init__(self, on_progress):
        if ProgressBarLogger:
            super().__init__()
        self.on_progress = on_progress
        self._last_pct = -1

    def bars_callback(self, bar, attr, value, old_value=None):
        try:
            total = self.bars[bar].get("total") or 0
            if attr == "index" and total:
                pct = max(0, min(100, int(100 * value / total)))
                if pct != self._last_pct:
                    self._last_pct = pct
                    self.on_progress(pct)
        except Exception:
            pass


# ---------------------------------------------------------------------------
#  COLOUR TOKENS (Dark Studio Palette)
# ---------------------------------------------------------------------------
C = {
    "bg": "#121212",
    "surface": "#1a1a1a",
    "panel": "#1e1e1e",
    "raised": "#2a2a2a",
    "border": "#333333",
    "accent": "#00c8ff",
    "accent2": "#ff3cac",
    "accent3": "#39d353",
    "accent4": "#FF9800",
    "danger": "#E91E63",
    "text": "#ffffff",
    "text_dim": "#aaaaaa",
    "clip_video": "#1e4d7a",
    "clip_bgm": "#4a1a6e",
    "clip_mute": "#8B0000",
    "waveform": "#00c8ff",
}


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tw:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tw,
            text=self.text,
            bg="#333",
            fg="white",
            font=("Arial", 9),
            relief="solid",
            bd=1,
            padx=6,
            pady=3,
        ).pack()

    def hide(self, _=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None


def icon_btn(parent, text, tip, cmd, bg=None, fg="white", w=None):
    kw = dict(
        text=text,
        command=cmd,
        bg=bg or C["raised"],
        fg=fg,
        font=("Segoe UI Emoji", 11),
        relief="flat",
        activebackground=C["border"],
        activeforeground="white",
        cursor="hand2",
        bd=0,
        padx=6,
        pady=4,
    )
    if w:
        kw["width"] = w
    b = tk.Button(parent, **kw)
    Tooltip(b, tip)
    return b


def create_scroll_canvas(parent, bg_color):
    canvas = tk.Canvas(parent, bg=bg_color, highlightthickness=0)
    scroll = tk.Scrollbar(
        parent,
        orient=tk.VERTICAL,
        command=canvas.yview,
        bg="#555555",
        troughcolor="#222222",
        activebackground="#888888",
        width=16,
        bd=0,
        highlightthickness=0,
        relief="flat",
    )
    inner = tk.Frame(canvas, bg=bg_color)

    def _update_scrollregion(e=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    inner.bind("<Configure>", _update_scrollregion)
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scroll.set)

    def _on_configure(e):
        canvas.itemconfig("all", width=e.width)
        _update_scrollregion()

    canvas.bind("<Configure>", _on_configure)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_wheel(e):
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_wheel(e):
        canvas.unbind_all("<MouseWheel>")

    canvas.bind("<Enter>", _bind_wheel)
    canvas.bind("<Leave>", _unbind_wheel)
    inner.bind("<Enter>", _bind_wheel)
    inner.bind("<Leave>", _unbind_wheel)
    parent.bind("<Enter>", _bind_wheel)
    parent.bind("<Leave>", _unbind_wheel)

    return canvas, inner


def extract_waveform_samples(path, n_samples=200):
    if not _MOVIEPY_LOADED:
        return None
    try:
        ext = path.lower().split(".")[-1]
        if ext in ("mp4", "mov", "avi", "mkv", "webm"):
            clip = VideoFileClip(path)
            audio = clip.audio
        else:
            audio = AudioFileClip(path)

        if audio is None:
            return None

        dur = audio.duration
        times = np.linspace(0, dur - 1 / 44100, n_samples)
        frames = np.array([audio.get_frame(t) for t in times])

        if frames.ndim == 2:
            frames = frames.mean(axis=1)
        frames = np.abs(frames)
        mx = frames.max()
        if mx > 0:
            frames /= mx

        if ext in ("mp4", "mov", "avi", "mkv", "webm"):
            clip.close()
        else:
            audio.close()

        return frames
    except Exception:
        return None
