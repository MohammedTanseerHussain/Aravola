from __future__ import annotations

from pathlib import Path

from PIL import Image

from videomerger.models import Clip, Project
from videomerger.render.export import export_project, prepare_project
from videomerger.render.frame import FrameRenderer, apply_clip_look, render_clip_frame


def _project(sample_video: str) -> Project:
    project = Project(name="render", width=160, height=120, fps=12)
    project.add_clip(Clip(kind="video", path=sample_video, name="a"))
    project.add_clip(Clip(kind="title", duration=0.5,
                          title={"main_text": "TITLE", "sub_text": "sub"}))
    prepare_project(project)
    project.reflow()
    return project


def test_render_clip_frame(sample_video):
    project = _project(sample_video)
    image = render_clip_frame(project.clips[0], 0.2, 160, 120)
    assert image.size == (160, 120)
    assert image.mode == "RGB"


def test_frame_renderer_timeline(sample_video):
    project = _project(sample_video)
    with FrameRenderer(project) as renderer:
        first = renderer.render(0.1)
        second = renderer.render(1.2)
        assert first.size == (160, 120)
        assert second.size == (160, 120)


def test_apply_clip_look_with_effect(sample_video):
    project = _project(sample_video)
    clip = project.clips[0]
    clip.effects = {"color_filter": {"style": "BW Memories", "enabled": True}}
    image = render_clip_frame(clip, 0.2, 160, 120)
    assert image.size == (160, 120)


def test_export_project(sample_video, tmp_path: Path):
    project = _project(sample_video)
    project.clips[0].trim_end = 0.6
    project.reflow()
    output = tmp_path / "out.mp4"
    result = export_project(project, str(output), fps=8, preset="ultrafast")
    assert Path(result).exists()
    assert output.stat().st_size > 0
