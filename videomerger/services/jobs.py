"""Background export jobs.

Exports are heavy and long-running, so the API returns a job id immediately and
the client polls ``/api/jobs/{id}``.  A single worker keeps memory use
predictable; raise ``max_workers`` for a multi-GPU deployment.
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import Project
from ..render.export import ExportCancelled, export_project


def _job_id() -> str:
    return f"job_{uuid.uuid4().hex[:12]}"


@dataclass
class Job:
    id: str = field(default_factory=_job_id)
    kind: str = "export"
    status: str = "queued"  # queued | running | done | error | cancelled
    progress: float = 0.0
    output_path: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    future: Future | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(float(self.progress), 4),
            "output_path": self.output_path,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "meta": self.meta,
            "download_url": (
                f"/api/jobs/{self.id}/download" if self.status == "done" else None
            ),
        }


class JobManager:
    def __init__(self, max_workers: int = 1) -> None:
        self._max_workers = max(1, int(max_workers))
        self._executor: ThreadPoolExecutor | None = None
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()

    def _ensure_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers, thread_name_prefix="vm-export"
            )
        return self._executor

    def submit_export(
        self,
        project: Project,
        output_path: str,
        *,
        fps: int | None = None,
        codec: str = "libx264",
        audio_codec: str = "aac",
        preset: str = "ultrafast",
        threads: int | None = None,
    ) -> Job:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        job = Job(
            kind="export",
            meta={
                "project_id": project.id,
                "project_name": project.name,
                "fps": fps or project.fps,
                "preset": preset,
                "clips": len(project.clips),
                "duration": round(project.total_duration(), 3),
            },
        )
        # Snapshot the project so later edits cannot change a running export.
        snapshot = project.copy()
        with self._lock:
            self._jobs[job.id] = job
            executor = self._ensure_executor()
        job.future = executor.submit(
            self._run_export, job, snapshot, str(output),
            fps, codec, audio_codec, preset, threads,
        )
        return job

    def _run_export(
        self,
        job: Job,
        project: Project,
        output_path: str,
        fps: int | None,
        codec: str,
        audio_codec: str,
        preset: str,
        threads: int | None,
    ) -> None:
        with self._lock:
            job.status = "running"
            job.started_at = time.time()
        try:
            def on_progress(value: float) -> None:
                with self._lock:
                    job.progress = max(job.progress, min(1.0, float(value)))

            export_project(
                project,
                output_path,
                fps=fps,
                codec=codec,
                audio_codec=audio_codec,
                preset=preset,
                threads=threads,
                progress=on_progress,
                cancel_event=job.cancel_event,
            )
            with self._lock:
                if job.cancel_event.is_set():
                    job.status = "cancelled"
                    job.error = "export cancelled"
                else:
                    job.status = "done"
                    job.progress = 1.0
                    job.output_path = output_path
        except ExportCancelled:
            with self._lock:
                job.status = "cancelled"
                job.error = "export cancelled"
        except Exception as exc:  # pragma: no cover - surfaced through API
            with self._lock:
                job.status = "error"
                job.error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                job.finished_at = time.time()
                try:
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"job not found: {job_id}")
            return job

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return [job.to_dict() for job in jobs]

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        with self._lock:
            if job.status in {"done", "error", "cancelled"}:
                return job
            job.cancel_event.set()
            if job.status == "queued" and job.future is not None and job.future.cancel():
                job.status = "cancelled"
                job.finished_at = time.time()
            else:
                job.status = "cancelling"
            return job

    def remove(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status in {"running", "cancelling"}:
                job.cancel_event.set()
            self._jobs.pop(job_id, None)
            return True

    def shutdown(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                if job.status in {"queued", "running", "cancelling"}:
                    job.cancel_event.set()
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)


JOBS = JobManager(max_workers=1)
