"""Central configuration and filesystem layout.

Import this module instead of hard-coding paths in feature modules.  Every
path is resolved from the project root, so the backend can be started from any
working directory (including a deployed container).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
MODELS = ASSETS / "models"
ACCESSORIES = ASSETS / "accessories"
REFERENCE = ASSETS / "reference"
UPLOADS = ROOT / "uploads"
OUTPUT = ROOT / "output"
JOBS = OUTPUT / "jobs"
PREVIEWS = OUTPUT / "previews"

for directory in (ASSETS, MODELS, ACCESSORIES, REFERENCE, UPLOADS, OUTPUT, JOBS, PREVIEWS):
    directory.mkdir(parents=True, exist_ok=True)

# ImageMagick is only used by MoviePy's TextClip.  The new renderer draws text
# with Pillow, but keeping the variable set helps legacy scripts that still use
# TextClip on Windows.
_IMAGEMAGICK = Path(r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe")
if _IMAGEMAGICK.exists():
    os.environ.setdefault("IMAGEMAGICK_BINARY", str(_IMAGEMAGICK))


def _first_existing(*candidates: Path) -> Path | None:
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


HAAR_CASCADE = _first_existing(MODELS / "haarcascade_frontalface_default.xml")

SEGMENTER_MODEL = _first_existing(MODELS / "selfie_segmenter.tflite")

YOLO_MODEL = _first_existing(MODELS / "yolov8n-seg.pt")

# Accessory assets (transparent PNGs) used by the thug-life effect.
GLASSES_PIXEL = _first_existing(ACCESSORIES / "glasses_pixel.png")
GLASSES_REAL = _first_existing(ACCESSORIES / "glasses_real.png")
CHAIN_PIXEL = _first_existing(ACCESSORIES / "chain_pixel.png")
CHAIN_REAL = _first_existing(ACCESSORIES / "chain_real.png")
CAP = _first_existing(ACCESSORIES / "cap_pixel.png")

OUTPUT_FPS = 30
AUDIO_SAMPLE_RATE = 44100

# Video extensions accepted by the media library.
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg"}


def ffmpeg_binary() -> str:
    """Return a usable ffmpeg executable name/path."""
    env = os.environ.get("FFMPEG_BINARY")
    if env:
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in (
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    # MoviePy bundles an ffmpeg binary through imageio-ffmpeg.
    try:
        from moviepy.config import get_setting  # type: ignore

        bundled = Path(get_setting("FFMPEG_BINARY"))
        if bundled.exists():
            return str(bundled)
    except Exception:
        pass
    return "ffmpeg"


def ffprobe_binary() -> str:
    """Return a usable ffprobe executable name/path."""
    env = os.environ.get("FFPROBE_BINARY")
    if env:
        return env
    found = shutil.which("ffprobe")
    if found:
        return found
    for candidate in (
        Path(r"C:\ffmpeg\bin\ffprobe.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffprobe.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    # MoviePy bundles ffmpeg but not always ffprobe; try its sibling.
    try:
        from moviepy.config import get_setting  # type: ignore

        sibling = Path(get_setting("FFMPEG_BINARY")).with_name("ffprobe.exe")
        if sibling.exists():
            return str(sibling)
    except Exception:
        pass
    return "ffprobe"
