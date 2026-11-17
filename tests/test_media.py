from __future__ import annotations

from pathlib import Path

import numpy as np

from videomerger.media import (
    extract_audio,
    filmstrip,
    probe,
    read_frame,
    thumbnail,
    waveform_samples,
)


def test_probe_video_reads_metadata(sample_video):
    info = probe(sample_video)
    assert info.kind == "video"
    assert info.has_video
    assert info.has_audio
    assert info.width == 160
    assert info.height == 120
    assert info.duration > 0.5


def test_read_frame_and_thumbnail(sample_video):
    frame = read_frame(sample_video, 0.2)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (120, 160, 3)
    assert frame.dtype == np.uint8

    image = thumbnail(sample_video, 0.2, (80, 60))
    assert image.size == (80, 60)


def test_filmstrip(sample_video):
    strip = filmstrip(sample_video, frames=3, thumb_size=(40, 30))
    assert strip.size == (120, 30)


def test_waveform_samples(sample_video, silent_video):
    samples = waveform_samples(sample_video, samples=16)
    assert len(samples) == 16
    assert max(samples) <= 1.0
    assert max(samples) > 0.05
    assert waveform_samples(silent_video, samples=8) == [0.0] * 8


def test_extract_audio(sample_video, tmp_path: Path):
    output = tmp_path / "audio.wav"
    extract_audio(sample_video, str(output))
    assert output.exists()
    assert probe(str(output)).duration > 0.5
