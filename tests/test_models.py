from __future__ import annotations

from videomerger.models import AudioTrack, Clip, Project, Transform


def test_video_effective_duration_respects_trim_and_speed():
    clip = Clip(kind="video", path="x.mp4", source_duration=10.0, trim_start=2.0,
                trim_end=8.0, speed=2.0)
    assert clip.effective_duration() == 3.0
    assert clip.local_time(1.0) == 4.0


def test_image_duration_uses_speed():
    clip = Clip(kind="image", path="x.png", duration=6.0, speed=2.0)
    assert clip.effective_duration() == 3.0


def test_split_video_preserves_right_trim_end():
    clip = Clip(kind="video", path="x.mp4", source_duration=10.0,
                trim_start=1.0, trim_end=9.0, timeline_start=0.0)
    project = Project(clips=[clip])
    left, right = project.split_clip(clip.id, 2.0)
    assert left.trim_end == 3.0
    assert right.trim_start == 3.0
    assert right.trim_end == 9.0
    assert right.timeline_start == 2.0
    assert project.clips == [left, right]


def test_split_title_clip_uses_duration():
    clip = Clip(kind="title", duration=4.0)
    project = Project(clips=[clip])
    left, right = project.split_clip(clip.id, 1.5)
    assert left.duration == 1.5
    assert right.duration == 2.5


def test_legacy_dict_aliases():
    clip = Clip.from_legacy_dict({
        "type": "video",
        "path": "x.mp4",
        "clip_start": 1.5,
        "clip_end": 4.5,
        "tl_start": 2.0,
        "trans": "Hard Cut",
        "x_offset": 12,
        "y_offset": -8,
        "effect_film_burn_enabled": True,
    })
    assert clip.kind == "video"
    assert clip.trim_start == 1.5
    assert clip.trim_end == 4.5
    assert clip.timeline_start == 2.0
    assert clip.transition == "Hard Cut"
    assert clip.transform.x == 12
    assert clip.transform.y == -8
    assert clip.extra["effect_film_burn_enabled"] is True


def test_project_roundtrip():
    project = Project(name="roundtrip", format="portrait", fps=24)
    project.add_clip(Clip(kind="image", path="a.png", duration=2.0,
                          transform=Transform(scale=1.2, rotation=90)))
    project.add_audio(AudioTrack(path="a.mp3", volume=0.4, start_offset=1.0))
    restored = Project.from_dict(project.to_dict())
    assert restored.id == project.id
    assert restored.format == "portrait"
    assert restored.width == 1080
    assert restored.height == 1920
    assert restored.clips[0].transform.scale == 1.2
    assert restored.clips[0].transform.rotation == 90
    assert restored.audio_tracks[0].volume == 0.4


def test_reflow_lays_clips_back_to_back():
    project = Project(clips=[
        Clip(kind="image", path="a.png", duration=2.0),
        Clip(kind="image", path="b.png", duration=3.0),
    ])
    project.reflow(start=1.0)
    assert [round(c.timeline_start, 3) for c in project.clips] == [1.0, 3.0]
    assert project.total_duration() == 6.0


def test_validation_reports_missing_paths():
    project = Project(clips=[Clip(kind="video", path="", source_duration=2.0)])
    errors = project.validate()
    assert any("missing path" in error for error in errors)
