"""In-memory project store with undo/redo.

The API is stateless-ish: a client downloads or keeps the project JSON, and the
server keeps live copies while editing.  Swap this module for a database-backed
repository later without touching the renderer or effect libraries.
"""
from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..media import probe
from ..models import AudioTrack, Clip, Project, Transform


@dataclass
class ProjectRecord:
    project: Project
    undo: list[dict[str, Any]] = field(default_factory=list)
    redo: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.project.id,
            "name": self.project.name,
            "format": self.project.format,
            "width": self.project.width,
            "height": self.project.height,
            "fps": self.project.fps,
            "duration": round(self.project.total_duration(), 3),
            "clip_count": len(self.project.clips),
            "audio_track_count": len(self.project.audio_tracks),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "can_undo": bool(self.undo),
            "can_redo": bool(self.redo),
        }


class ProjectStore:
    def __init__(self) -> None:
        self._records: dict[str, ProjectRecord] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create(self, data: dict[str, Any] | None = None) -> Project:
        project = Project.from_dict(data or {})
        with self._lock:
            self._records[project.id] = ProjectRecord(project=project)
        return project

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            records = sorted(self._records.values(), key=lambda r: r.updated_at, reverse=True)
            return [record.summary() for record in records]

    def get_record(self, project_id: str) -> ProjectRecord:
        with self._lock:
            record = self._records.get(project_id)
            if record is None:
                raise KeyError(f"project not found: {project_id}")
            return record

    def get(self, project_id: str) -> Project:
        return self.get_record(project_id).project

    def replace(self, project_id: str, data: dict[str, Any], *, snapshot: bool = True) -> Project:
        record = self.get_record(project_id)
        with self._lock:
            if snapshot:
                self._snapshot(record)
            incoming = Project.from_dict({**data, "id": project_id})
            record.project = incoming
            record.updated_at = time.time()
            return incoming

    def delete(self, project_id: str) -> bool:
        with self._lock:
            return self._records.pop(project_id, None) is not None

    def duplicate(self, project_id: str) -> Project:
        record = self.get_record(project_id)
        data = copy.deepcopy(record.project.to_dict())
        data["id"] = None
        data["name"] = f"{record.project.name} (copy)"
        return self.create(data)

    # ------------------------------------------------------------------
    # undo / redo
    # ------------------------------------------------------------------
    def _snapshot(self, record: ProjectRecord) -> None:
        record.undo.append(copy.deepcopy(record.project.to_dict()))
        if len(record.undo) > 50:
            record.undo.pop(0)
        record.redo.clear()
        record.updated_at = time.time()

    def save_state(self, project_id: str) -> None:
        record = self.get_record(project_id)
        with self._lock:
            self._snapshot(record)

    def undo(self, project_id: str) -> Project | None:
        record = self.get_record(project_id)
        with self._lock:
            if not record.undo:
                return None
            record.redo.append(copy.deepcopy(record.project.to_dict()))
            data = record.undo.pop()
            record.project = Project.from_dict(data)
            record.updated_at = time.time()
            return record.project

    def redo(self, project_id: str) -> Project | None:
        record = self.get_record(project_id)
        with self._lock:
            if not record.redo:
                return None
            record.undo.append(copy.deepcopy(record.project.to_dict()))
            data = record.redo.pop()
            record.project = Project.from_dict(data)
            record.updated_at = time.time()
            return record.project

    # ------------------------------------------------------------------
    # editing helpers
    # ------------------------------------------------------------------
    def add_clip(
        self,
        project_id: str,
        payload: dict[str, Any],
        *,
        index: int | None = None,
        probe_media: bool = True,
    ) -> Clip:
        record = self.get_record(project_id)
        with self._lock:
            self._snapshot(record)
            clip = Clip.from_dict(payload)
            if probe_media and clip.path and clip.kind in {"video", "image"}:
                info = probe(clip.path)
                if clip.kind == "video" and info.duration > 0:
                    clip.source_duration = info.duration
                    if clip.trim_end is None:
                        clip.trim_end = info.duration
                    clip.duration = clip.effective_duration()
                elif clip.kind == "image" and info.width:
                    clip.name = clip.name or info.path.split("\\")[-1].split("/")[-1]
            record.project.add_clip(clip, index)
            record.updated_at = time.time()
            return clip

    def update_clip(self, project_id: str, clip_id: str, payload: dict[str, Any]) -> Clip:
        record = self.get_record(project_id)
        with self._lock:
            clip = record.project.find_clip(clip_id)
            if clip is None:
                raise KeyError(f"clip not found: {clip_id}")
            self._snapshot(record)
            self._apply_clip_patch(clip, payload)
            record.updated_at = time.time()
            return clip

    @staticmethod
    def _apply_clip_patch(clip: Clip, payload: dict[str, Any]) -> None:
        known = set(Clip.__dataclass_fields__)  # type: ignore[attr-defined]
        for key, value in payload.items():
            if key == "transform" and isinstance(value, dict):
                merged = {**clip.transform.__dict__, **value}
                clip.transform = Transform.from_dict(merged)
            elif key == "effects" and isinstance(value, dict):
                merged = copy.deepcopy(clip.effects)
                merged.update(copy.deepcopy(value))
                clip.effects = merged
            elif key == "title" and isinstance(value, dict):
                clip.title = {**clip.title, **copy.deepcopy(value)}
            elif key == "extra" and isinstance(value, dict):
                clip.extra = {**clip.extra, **copy.deepcopy(value)}
            elif key in known:
                setattr(clip, key, value)
            else:
                clip.extra[key] = value

    def remove_clip(self, project_id: str, clip_id: str) -> bool:
        record = self.get_record(project_id)
        with self._lock:
            self._snapshot(record)
            removed = record.project.remove_clip(clip_id)
            record.updated_at = time.time()
            return removed

    def move_clip(self, project_id: str, clip_id: str, index: int) -> bool:
        record = self.get_record(project_id)
        with self._lock:
            self._snapshot(record)
            moved = record.project.move_clip(clip_id, index)
            record.updated_at = time.time()
            return moved

    def split_clip(self, project_id: str, clip_id: str, at_time: float) -> tuple[Clip, Clip] | None:
        record = self.get_record(project_id)
        with self._lock:
            self._snapshot(record)
            result = record.project.split_clip(clip_id, float(at_time))
            record.updated_at = time.time()
            return result

    def reflow(self, project_id: str, start: float = 0.0) -> Project:
        record = self.get_record(project_id)
        with self._lock:
            self._snapshot(record)
            record.project.reflow(start)
            record.updated_at = time.time()
            return record.project

    def add_audio(
        self,
        project_id: str,
        payload: dict[str, Any],
        *,
        index: int | None = None,
        probe_media: bool = True,
    ) -> AudioTrack:
        record = self.get_record(project_id)
        with self._lock:
            self._snapshot(record)
            track = AudioTrack.from_dict(payload)
            if probe_media and track.path:
                info = probe(track.path)
                if info.duration > 0:
                    track.source_duration = info.duration
                    if track.trim_end is None:
                        track.trim_end = info.duration
            record.project.add_audio(track, index)
            record.updated_at = time.time()
            return track

    def update_audio(self, project_id: str, track_id: str, payload: dict[str, Any]) -> AudioTrack:
        record = self.get_record(project_id)
        with self._lock:
            track = record.project.find_audio(track_id)
            if track is None:
                raise KeyError(f"audio track not found: {track_id}")
            self._snapshot(record)
            known = set(AudioTrack.__dataclass_fields__)  # type: ignore[attr-defined]
            for key, value in payload.items():
                if key in known:
                    setattr(track, key, value)
                else:
                    track.extra[key] = value
            record.updated_at = time.time()
            return track

    def remove_audio(self, project_id: str, track_id: str) -> bool:
        record = self.get_record(project_id)
        with self._lock:
            self._snapshot(record)
            removed = record.project.remove_audio(track_id)
            record.updated_at = time.time()
            return removed

    def update_project(self, project_id: str, payload: dict[str, Any]) -> Project:
        record = self.get_record(project_id)
        with self._lock:
            self._snapshot(record)
            project = record.project
            for key in ("name", "format", "width", "height", "fps", "smart_fill", "auto_rotate"):
                if key in payload:
                    setattr(project, key, payload[key])
            if not payload.get("width") and not payload.get("height") and "format" in payload:
                project.width = project.height = 0
                project.__post_init__()
            record.updated_at = time.time()
            return project

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


STORE = ProjectStore()
