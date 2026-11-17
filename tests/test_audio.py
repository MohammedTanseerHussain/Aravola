from __future__ import annotations

from pathlib import Path

from videomerger.audio import build_audio_mix, detect_silence, eval_envelope, mix_audio
from videomerger.models import AudioTrack, Clip, Project
from videomerger.render.export import prepare_project


def test_eval_envelope_interpolates_and_clamps():
    points = [[0.0, 0.2], [1.0, 1.0]]
    assert eval_envelope(points, 0.0) == 0.2
    assert eval_envelope(points, 1.0) == 1.0
    assert 0.2 < eval_envelope(points, 0.5) < 1.0
    assert eval_envelope([], 0.5, 0.7) == 0.7


def test_build_audio_mix_returns_none_for_silent_project(silent_video):
    project = Project(width=160, height=120, fps=12)
    project.add_clip(Clip(kind="video", path=silent_video))
    prepare_project(project)
    project.reflow()
    assert build_audio_mix(project) is None


def test_mix_audio_writes_wav(sample_video, tmp_path: Path):
    project = Project(width=160, height=120, fps=12)
    project.add_clip(Clip(kind="video", path=sample_video))
    project.add_audio(AudioTrack(path=sample_video, volume=0.5, start_offset=0.2))
    prepare_project(project)
    project.reflow()
    output = tmp_path / "mix.wav"
    assert mix_audio(project, str(output)) == str(output)
    assert output.exists()
    assert output.stat().st_size > 0


def test_detect_silence_returns_pairs(sample_video):
    ranges = detect_silence(sample_video, samples=64)
    assert isinstance(ranges, list)
    for start, end in ranges:
        assert end >= start
