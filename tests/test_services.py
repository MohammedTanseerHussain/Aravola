from __future__ import annotations

from videomerger.services.projects import ProjectStore


def test_store_create_add_update_undo_redo(sample_video):
    store = ProjectStore()
    project = store.create({"name": "store", "width": 160, "height": 120, "fps": 12})
    clip = store.add_clip(project.id, {"kind": "video", "path": sample_video})
    assert clip.source_duration > 0
    assert store.get(project.id).clips[0].id == clip.id

    store.update_clip(project.id, clip.id, {"volume": 0.25, "transform": {"scale": 1.5}})
    assert store.get(project.id).clips[0].volume == 0.25
    assert store.get(project.id).clips[0].transform.scale == 1.5

    restored = store.undo(project.id)
    assert restored is not None
    assert store.get(project.id).clips[0].volume == 1.0

    redone = store.redo(project.id)
    assert redone is not None
    assert store.get(project.id).clips[0].volume == 0.25


def test_store_split_and_reflow(sample_video):
    store = ProjectStore()
    project = store.create({"name": "split", "width": 160, "height": 120, "fps": 12})
    clip = store.add_clip(project.id, {"kind": "video", "path": sample_video})
    result = store.split_clip(project.id, clip.id, 0.5)
    assert result is not None
    left, right = result
    assert left.trim_end == 0.5
    assert right.trim_start == 0.5
    store.reflow(project.id)
    assert store.get(project.id).clips[0].timeline_start == 0.0
    assert store.get(project.id).clips[1].timeline_start == 0.5


def test_store_update_project_format():
    store = ProjectStore()
    project = store.create({"name": "format", "width": 160, "height": 120, "fps": 12})
    updated = store.update_project(project.id, {"format": "portrait"})
    assert updated.width == 1080
    assert updated.height == 1920


def test_store_duplicate(sample_video):
    store = ProjectStore()
    project = store.create({"name": "copy me", "width": 160, "height": 120, "fps": 12})
    duplicate = store.duplicate(project.id)
    assert duplicate.id != project.id
    assert duplicate.name.endswith("(copy)")
