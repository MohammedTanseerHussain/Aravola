from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="session")
def sample_video(media_dir: Path) -> str:
    from moviepy.editor import AudioClip, ColorClip

    audio = AudioClip(
        lambda t: 0.15 * np.sin(2 * np.pi * 440 * np.asarray(t)),
        duration=1.0,
        fps=44100,
    )
    clip = ColorClip((160, 120), color=(50, 120, 200), duration=1.0).set_audio(audio)
    path = media_dir / "sample.mp4"
    clip.write_videofile(str(path), fps=12, preset="ultrafast", logger=None)
    clip.close()
    return str(path)


@pytest.fixture(scope="session")
def silent_video(media_dir: Path) -> str:
    from moviepy.editor import ColorClip

    clip = ColorClip((160, 120), color=(200, 80, 40), duration=1.0)
    path = media_dir / "silent.mp4"
    clip.write_videofile(str(path), fps=12, preset="ultrafast", logger=None)
    clip.close()
    return str(path)


@pytest.fixture(scope="session")
def sample_image(media_dir: Path) -> str:
    image = Image.new("RGB", (240, 160), (30, 140, 90))
    path = media_dir / "sample.png"
    image.save(path)
    return str(path)


@pytest.fixture()
def frame() -> np.ndarray:
    return np.full((120, 160, 3), 80, dtype=np.uint8)
