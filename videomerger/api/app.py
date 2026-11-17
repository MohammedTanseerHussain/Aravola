"""FastAPI application.

Every feature library in :mod:`videomerger` is exposed here as an endpoint, so
a web frontend (or a test script) can call the same code the desktop app uses.

Run with::

    python run_api.py
    # or
    uvicorn videomerger.api.app:app --reload
"""
from __future__ import annotations

import base64
import io
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import numpy as np
from PIL import Image

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from .. import __version__
from ..audio import detect_silence, mix_audio
from ..config import (
    ACCESSORIES,
    JOBS,
    MODELS,
    OUTPUT,
    ROOT,
    UPLOADS,
    ffmpeg_binary,
    ffprobe_binary,
)
from ..effects import EFFECTS, apply_effect, list_effects
from ..media import filmstrip, probe, read_frame, thumbnail, waveform_samples
from ..models import Project
from ..render.export import export_project, prepare_project
from ..render.frame import FrameRenderer
from ..services import JOBS as JOB_MANAGER
from ..services import STORE
from ..titles import render_lower_third, render_title_card
from ..vision import detect_faces, detect_persons, person_mask, select_person
from .schemas import (
    AddAudioRequest,
    AddClipRequest,
    AudioMixRequest,
    AudioPayload,
    ClipPatch,
    EffectApplyRequest,
    EffectSlotRequest,
    ExportRequest,
    LowerThirdRequest,
    MoveRequest,
    PreviewRequest,
    ProbeRequest,
    ProjectPatch,
    ProjectPayload,
    ReflowRequest,
    SilenceRequest,
    SplitRequest,
    TitleRequest,
    VisionRequest,
)

TITLE_THEMES = [
    "Cinematic – Deep Space Stars",
    "Cinematic – Light Speed Burst",
    "Cinematic – Travelling Lens Flare",
    "Cinematic – Aurora",
]
LOWER_THIRD_STYLES = [
    "Static Aurora Tile (Bracket)",
    "News Headline",
    "Purple Designer Box",
    "Magical Aurora",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _payload(model) -> dict[str, Any]:
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    return model.dict(exclude_none=True)  # pydantic v1 fallback


def _get_project(project_id: str) -> Project:
    try:
        return STORE.get(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _media_path(value: str | Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"file not found: {path}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"not a file: {path}")
    return path


def _decode_base64_image(value: str) -> np.ndarray:
    data = value.strip()
    if data.startswith("data:"):
        _, _, data = data.partition(",")
    try:
        raw = base64.b64decode(data)
        with Image.open(io.BytesIO(raw)) as image:
            return np.array(image.convert("RGB"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid image_base64: {exc}") from exc


def _input_frame(path: str | None, image_base64: str | None, time_value: float) -> np.ndarray:
    if image_base64:
        return _decode_base64_image(image_base64)
    if path:
        return read_frame(str(_media_path(path)), float(time_value))
    raise HTTPException(status_code=400, detail="provide either 'path' or 'image_base64'")


def _png_response(image: Image.Image | np.ndarray) -> Response:
    if isinstance(image, np.ndarray):
        array = image
        if array.dtype != np.uint8:
            array = np.clip(array, 0, 255).astype(np.uint8)
        image = Image.fromarray(array)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store", "Content-Disposition": "inline; filename=preview.png"},
    )


def _slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return cleaned.strip("_")[:60] or "export"


def _unique_output(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "export.mp4"
    if not Path(safe_name).suffix:
        safe_name += ".mp4"
    candidate = directory / safe_name
    stem, suffix = candidate.stem, candidate.suffix
    index = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{index}{suffix}"
        index += 1
    return candidate


def _summary(project: Project) -> dict[str, Any]:
    data = project.to_dict()
    data["duration"] = round(project.total_duration(), 4)
    return data


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    JOB_MANAGER.shutdown()


# ---------------------------------------------------------------------------
# app factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title="VideoMerger API",
        version=__version__,
        description=(
            "Headless backend for the VideoMerger desktop studio. Each endpoint maps "
            "to a small, independently testable feature library."
        ),
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(KeyError)
    async def _key_error(_request: Request, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(FileNotFoundError)
    async def _file_error(_request: Request, exc: FileNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # ------------------------------------------------------------------
    # service / catalog
    # ------------------------------------------------------------------
    @app.get("/", tags=["service"])
    def root() -> dict[str, Any]:
        return {
            "service": "videomerger",
            "version": __version__,
            "docs": "/docs",
            "openapi": "/openapi.json",
        }

    @app.get("/health", tags=["service"])
    @app.get("/api/health", tags=["service"])
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "videomerger", "version": __version__}

    @app.get("/api/capabilities", tags=["service"])
    def capabilities() -> dict[str, Any]:
        def module_version(name: str) -> str | None:
            try:
                module = __import__(name)
                return getattr(module, "__version__", None)
            except Exception:
                return None

        return {
            "version": __version__,
            "ffmpeg": ffmpeg_binary(),
            "ffprobe": ffprobe_binary(),
            "models": {
                "haar_face": (MODELS / "haarcascade_frontalface_default.xml").exists()
                or (ROOT / "haarcascade_frontalface_default.xml").exists(),
                "mediapipe_segmenter": (MODELS / "selfie_segmenter.tflite").exists()
                or (ROOT / "selfie_segmenter.tflite").exists(),
                "yolo_segmenter": (MODELS / "yolov8n-seg.pt").exists()
                or (ROOT / "yolov8n-seg.pt").exists(),
            },
            "accessories": sorted(p.name for p in ACCESSORIES.glob("*.png")),
            "title_themes": TITLE_THEMES,
            "lower_third_styles": LOWER_THIRD_STYLES,
            "effect_categories": sorted({spec["category"] for spec in EFFECTS.values()}),
            "dependencies": {
                name: module_version(name)
                for name in ("fastapi", "moviepy", "mediapipe", "ultralytics", "cv2", "PIL", "numpy")
            },
        }

    @app.get("/api/effects", tags=["effects"])
    def effects_catalogue() -> dict[str, Any]:
        return {"effects": list_effects()}

    @app.get("/api/effects/{effect_id}", tags=["effects"])
    def effect_metadata(effect_id: str) -> dict[str, Any]:
        spec = EFFECTS.get(effect_id)
        if spec is None:
            raise HTTPException(status_code=404, detail=f"unknown effect: {effect_id}")
        return {
            "id": effect_id,
            "label": spec["label"],
            "category": spec["category"],
            "animated": spec["animated"],
            "params": spec["params"],
            "needs_mask": spec.get("needs_mask", False),
            "needs_face": spec.get("needs_face", False),
            "needs_person": spec.get("needs_person", False),
        }

    @app.post("/api/effects/{effect_id}/apply", tags=["effects"])
    def apply_effect_endpoint(effect_id: str, body: EffectApplyRequest) -> Response:
        frame = _input_frame(body.path, body.image_base64, body.time)
        try:
            result = apply_effect(
                frame,
                effect_id,
                body.params,
                time=body.time,
                context=body.context or None,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _png_response(result)

    # ------------------------------------------------------------------
    # media
    # ------------------------------------------------------------------
    @app.post("/api/media/upload", tags=["media"])
    async def upload_media(file: UploadFile = File(...)) -> dict[str, Any]:
        filename = Path(file.filename or "upload").name
        target = UPLOADS / f"{uuid.uuid4().hex[:8]}_{filename}"
        with target.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        await file.close()
        return probe(str(target)).to_dict()

    @app.post("/api/media/probe", tags=["media"])
    def probe_media(body: ProbeRequest) -> dict[str, Any]:
        return probe(str(_media_path(body.path))).to_dict()

    @app.get("/api/media/probe", tags=["media"])
    def probe_media_query(path: str = Query(...)) -> dict[str, Any]:
        return probe(str(_media_path(path))).to_dict()

    @app.get("/api/media/thumbnail", tags=["media"])
    def media_thumbnail(
        path: str = Query(...),
        time: float = 0.0,
        width: int = 320,
        height: int = 180,
        smart_fill: bool = False,
    ) -> Response:
        image = thumbnail(str(_media_path(path)), time, (width, height), smart_fill=smart_fill)
        return _png_response(image)

    @app.get("/api/media/filmstrip", tags=["media"])
    def media_filmstrip(
        path: str = Query(...),
        frames: int = 3,
        width: int = 144,
        height: int = 80,
    ) -> Response:
        image = filmstrip(str(_media_path(path)), frames=frames, thumb_size=(width, height))
        return _png_response(image)

    @app.get("/api/media/frame", tags=["media"])
    def media_frame(
        path: str = Query(...),
        time: float = 0.0,
        width: int | None = None,
        height: int | None = None,
    ) -> Response:
        frame = read_frame(str(_media_path(path)), time)
        image = Image.fromarray(frame)
        if width or height:
            image = image.resize((width or image.width, height or image.height), Image.LANCZOS)
        return _png_response(image)

    @app.get("/api/media/waveform", tags=["media"])
    def media_waveform(path: str = Query(...), samples: int = 200) -> dict[str, Any]:
        return {"path": path, "samples": waveform_samples(str(_media_path(path)), samples)}

    # ------------------------------------------------------------------
    # projects
    # ------------------------------------------------------------------
    @app.get("/api/projects", tags=["projects"])
    def list_projects() -> dict[str, Any]:
        return {"projects": STORE.list()}

    @app.post("/api/projects", tags=["projects"], status_code=201)
    def create_project(body: ProjectPayload | None = None) -> dict[str, Any]:
        project = STORE.create(_payload(body))
        prepare_project(project, probe_files=False)
        return _summary(project)

    @app.get("/api/projects/{project_id}", tags=["projects"])
    def get_project(project_id: str) -> dict[str, Any]:
        project = _get_project(project_id)
        prepare_project(project, probe_files=False)
        return _summary(project)

    @app.put("/api/projects/{project_id}", tags=["projects"])
    def replace_project(project_id: str, body: ProjectPayload) -> dict[str, Any]:
        project = STORE.replace(project_id, _payload(body))
        prepare_project(project, probe_files=False)
        return _summary(project)

    @app.patch("/api/projects/{project_id}", tags=["projects"])
    def patch_project(project_id: str, body: ProjectPatch) -> dict[str, Any]:
        project = STORE.update_project(project_id, _payload(body))
        return _summary(project)

    @app.delete("/api/projects/{project_id}", tags=["projects"])
    def delete_project(project_id: str) -> dict[str, Any]:
        _get_project(project_id)
        STORE.delete(project_id)
        return {"deleted": project_id}

    @app.post("/api/projects/{project_id}/duplicate", tags=["projects"], status_code=201)
    def duplicate_project(project_id: str) -> dict[str, Any]:
        return _summary(STORE.duplicate(project_id))

    @app.get("/api/projects/{project_id}/timeline", tags=["projects"])
    def project_timeline(project_id: str) -> dict[str, Any]:
        project = _get_project(project_id)
        prepare_project(project, probe_files=False)
        clips = [
            {
                "index": index,
                "id": clip.id,
                "kind": clip.kind,
                "name": clip.name,
                "path": clip.path,
                "start": round(clip.timeline_start, 4),
                "duration": round(clip.effective_duration(), 4),
                "end": round(clip.timeline_end, 4),
                "trim_start": clip.trim_start,
                "trim_end": clip.trim_end,
                "speed": clip.speed,
                "transition": clip.transition,
                "transition_duration": clip.transition_duration,
                "muted": clip.muted,
                "volume": clip.volume,
            }
            for index, clip in enumerate(project.clips)
        ]
        audio = [
            {
                "id": track.id,
                "name": track.name,
                "path": track.path,
                "start": round(track.start_offset, 4),
                "duration": round(track.effective_duration(), 4),
                "end": round(track.timeline_end, 4),
                "muted": track.muted,
                "volume": track.volume,
            }
            for track in project.audio_tracks
        ]
        return {
            "project_id": project.id,
            "duration": round(project.total_duration(), 4),
            "clips": clips,
            "audio_tracks": audio,
        }

    @app.post("/api/projects/{project_id}/undo", tags=["projects"])
    def undo_project(project_id: str) -> dict[str, Any]:
        project = STORE.undo(project_id)
        if project is None:
            raise HTTPException(status_code=409, detail="nothing to undo")
        return _summary(project)

    @app.post("/api/projects/{project_id}/redo", tags=["projects"])
    def redo_project(project_id: str) -> dict[str, Any]:
        project = STORE.redo(project_id)
        if project is None:
            raise HTTPException(status_code=409, detail="nothing to redo")
        return _summary(project)

    @app.post("/api/projects/{project_id}/snapshot", tags=["projects"])
    def snapshot_project(project_id: str) -> dict[str, Any]:
        STORE.save_state(project_id)
        return {"saved": project_id}

    @app.post("/api/projects/{project_id}/reflow", tags=["projects"])
    def reflow_project(project_id: str, body: ReflowRequest | None = None) -> dict[str, Any]:
        start = 0.0 if body is None else body.start
        return _summary(STORE.reflow(project_id, start))

    # ---- clips -------------------------------------------------------
    @app.post("/api/projects/{project_id}/clips", tags=["clips"], status_code=201)
    def add_clip(project_id: str, body: AddClipRequest) -> dict[str, Any]:
        clip = STORE.add_clip(project_id, body.clip, index=body.index, probe_media=body.probe)
        return {"clip": clip.to_dict(), "project_duration": round(STORE.get(project_id).total_duration(), 4)}

    @app.post("/api/projects/{project_id}/media", tags=["clips"], status_code=201)
    async def add_media(
        project_id: str,
        file: UploadFile = File(...),
        index: int | None = None,
        transition: str = "Crossfade",
        transition_duration: float = 0.75,
    ) -> dict[str, Any]:
        _get_project(project_id)
        filename = Path(file.filename or "upload").name
        target = UPLOADS / f"{uuid.uuid4().hex[:8]}_{filename}"
        with target.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        await file.close()
        info = probe(str(target))
        clip_payload: dict[str, Any] = {
            "kind": info.kind if info.kind in {"video", "image"} else "video",
            "path": str(target),
            "name": filename,
            "transition": transition,
            "transition_duration": transition_duration,
        }
        clip = STORE.add_clip(project_id, clip_payload, index=index, probe_media=True)
        return {"media": info.to_dict(), "clip": clip.to_dict()}

    @app.patch("/api/projects/{project_id}/clips/{clip_id}", tags=["clips"])
    def patch_clip(project_id: str, clip_id: str, body: ClipPatch) -> dict[str, Any]:
        clip = STORE.update_clip(project_id, clip_id, _payload(body))
        return {"clip": clip.to_dict()}

    @app.delete("/api/projects/{project_id}/clips/{clip_id}", tags=["clips"])
    def delete_clip(project_id: str, clip_id: str) -> dict[str, Any]:
        removed = STORE.remove_clip(project_id, clip_id)
        if not removed:
            raise HTTPException(status_code=404, detail=f"clip not found: {clip_id}")
        return {"deleted": clip_id}

    @app.post("/api/projects/{project_id}/clips/{clip_id}/split", tags=["clips"])
    def split_clip(project_id: str, clip_id: str, body: SplitRequest) -> dict[str, Any]:
        result = STORE.split_clip(project_id, clip_id, body.time)
        if result is None:
            raise HTTPException(status_code=400, detail="split time is outside the clip")
        left, right = result
        return {"left": left.to_dict(), "right": right.to_dict()}

    @app.post("/api/projects/{project_id}/clips/reorder", tags=["clips"])
    def reorder_clip(project_id: str, body: MoveRequest) -> dict[str, Any]:
        moved = STORE.move_clip(project_id, body.clip_id, body.index)
        if not moved:
            raise HTTPException(status_code=404, detail=f"clip not found: {body.clip_id}")
        return {"project": _summary(STORE.get(project_id))}

    @app.put("/api/projects/{project_id}/clips/{clip_id}/effects/{effect_id}", tags=["clips"])
    def set_clip_effect(
        project_id: str,
        clip_id: str,
        effect_id: str,
        body: EffectSlotRequest,
    ) -> dict[str, Any]:
        if effect_id not in EFFECTS:
            raise HTTPException(status_code=404, detail=f"unknown effect: {effect_id}")
        params = dict(body.params)
        params["enabled"] = bool(body.enabled)
        clip = STORE.update_clip(project_id, clip_id, {"effects": {effect_id: params}})
        return {"clip": clip.to_dict()}

    @app.delete("/api/projects/{project_id}/clips/{clip_id}/effects/{effect_id}", tags=["clips"])
    def remove_clip_effect(project_id: str, clip_id: str, effect_id: str) -> dict[str, Any]:
        project = _get_project(project_id)
        clip = project.find_clip(clip_id)
        if clip is None:
            raise HTTPException(status_code=404, detail=f"clip not found: {clip_id}")
        effects = dict(clip.effects or {})
        effects.pop(effect_id, None)
        clip = STORE.update_clip(project_id, clip_id, {"effects": effects})
        # ``update_clip`` merges, so explicitly replace for removals.
        clip.effects = effects
        return {"clip": clip.to_dict()}

    # ---- audio -------------------------------------------------------
    @app.post("/api/projects/{project_id}/audio", tags=["audio"], status_code=201)
    def add_audio(project_id: str, body: AddAudioRequest) -> dict[str, Any]:
        track = STORE.add_audio(project_id, body.audio, index=body.index, probe_media=body.probe)
        return {"audio_track": track.to_dict()}

    @app.post("/api/projects/{project_id}/audio/upload", tags=["audio"], status_code=201)
    async def upload_audio(
        project_id: str,
        file: UploadFile = File(...),
        start_offset: float = 0.0,
        volume: float = 1.0,
    ) -> dict[str, Any]:
        _get_project(project_id)
        filename = Path(file.filename or "audio").name
        target = UPLOADS / f"{uuid.uuid4().hex[:8]}_{filename}"
        with target.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        await file.close()
        info = probe(str(target))
        track = STORE.add_audio(
            project_id,
            {
                "path": str(target),
                "name": filename,
                "start_offset": start_offset,
                "volume": volume,
            },
            probe_media=True,
        )
        return {"media": info.to_dict(), "audio_track": track.to_dict()}

    @app.patch("/api/projects/{project_id}/audio/{track_id}", tags=["audio"])
    def patch_audio(project_id: str, track_id: str, body: AudioPayload) -> dict[str, Any]:
        track = STORE.update_audio(project_id, track_id, _payload(body))
        return {"audio_track": track.to_dict()}

    @app.delete("/api/projects/{project_id}/audio/{track_id}", tags=["audio"])
    def delete_audio(project_id: str, track_id: str) -> dict[str, Any]:
        removed = STORE.remove_audio(project_id, track_id)
        if not removed:
            raise HTTPException(status_code=404, detail=f"audio track not found: {track_id}")
        return {"deleted": track_id}

    # ------------------------------------------------------------------
    # preview / render
    # ------------------------------------------------------------------
    @app.post("/api/projects/{project_id}/preview", tags=["render"])
    def preview_project(project_id: str, body: PreviewRequest) -> Response:
        project = _get_project(project_id)
        prepare_project(project, probe_files=False)
        renderer = FrameRenderer(project)
        try:
            image = renderer.render(body.time)
            if body.width or body.height:
                image = image.resize((body.width or image.width, body.height or image.height), Image.LANCZOS)
        finally:
            renderer.close()
        return _png_response(image)

    @app.get("/api/projects/{project_id}/preview.png", tags=["render"])
    def preview_project_png(
        project_id: str,
        time: float = 0.0,
        width: int | None = None,
        height: int | None = None,
    ) -> Response:
        project = _get_project(project_id)
        prepare_project(project, probe_files=False)
        renderer = FrameRenderer(project)
        try:
            image = renderer.render(time)
            if width or height:
                image = image.resize((width or image.width, height or image.height), Image.LANCZOS)
        finally:
            renderer.close()
        return _png_response(image)

    @app.post("/api/projects/{project_id}/export", tags=["render"], status_code=202)
    def export_project_endpoint(project_id: str, body: ExportRequest | None = None) -> dict[str, Any]:
        project = _get_project(project_id)
        request = body or ExportRequest()
        name = request.output_name or f"{_slug(project.name)}_{int(time.time())}.mp4"
        output = _unique_output(JOBS, name)
        job = JOB_MANAGER.submit_export(
            project,
            str(output),
            fps=request.fps,
            codec=request.codec,
            audio_codec=request.audio_codec,
            preset=request.preset,
            threads=request.threads,
        )
        return job.to_dict()

    @app.post("/api/projects/{project_id}/render", tags=["render"])
    def render_project_sync(project_id: str, body: ExportRequest | None = None) -> FileResponse:
        """Synchronous export for CLI-ish clients. Prefer the job endpoint."""
        project = _get_project(project_id)
        request = body or ExportRequest()
        name = request.output_name or f"{_slug(project.name)}_{int(time.time())}.mp4"
        output = _unique_output(JOBS, name)
        export_project(
            project,
            str(output),
            fps=request.fps,
            preset=request.preset,
            codec=request.codec,
            audio_codec=request.audio_codec,
            threads=request.threads,
        )
        return FileResponse(str(output), media_type="video/mp4", filename=output.name)

    # ------------------------------------------------------------------
    # jobs
    # ------------------------------------------------------------------
    @app.get("/api/jobs", tags=["jobs"])
    def list_jobs() -> dict[str, Any]:
        return {"jobs": JOB_MANAGER.list()}

    @app.get("/api/jobs/{job_id}", tags=["jobs"])
    def get_job(job_id: str) -> dict[str, Any]:
        return JOB_MANAGER.get(job_id).to_dict()

    @app.post("/api/jobs/{job_id}/cancel", tags=["jobs"])
    def cancel_job(job_id: str) -> dict[str, Any]:
        return JOB_MANAGER.cancel(job_id).to_dict()

    @app.delete("/api/jobs/{job_id}", tags=["jobs"])
    def delete_job(job_id: str) -> dict[str, Any]:
        removed = JOB_MANAGER.remove(job_id)
        if not removed:
            raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
        return {"deleted": job_id}

    @app.get("/api/jobs/{job_id}/download", tags=["jobs"])
    def download_job(job_id: str) -> FileResponse:
        job = JOB_MANAGER.get(job_id)
        if job.status != "done" or not job.output_path:
            raise HTTPException(status_code=409, detail=f"job is {job.status}, not ready")
        path = Path(job.output_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="output file is missing")
        return FileResponse(str(path), media_type="video/mp4", filename=path.name)

    # ------------------------------------------------------------------
    # titles
    # ------------------------------------------------------------------
    @app.post("/api/titles/card", tags=["titles"])
    def title_card(body: TitleRequest) -> Response:
        frame = render_title_card(
            body.width,
            body.height,
            body.main_text,
            body.sub_text,
            body.theme,
            time=body.time,
            duration=body.duration,
        )
        return _png_response(frame)

    @app.post("/api/titles/lower-third", tags=["titles"])
    def lower_third(body: LowerThirdRequest) -> Response:
        overlay = render_lower_third(
            body.text,
            body.width,
            body.height,
            body.style,
            time=body.time,
            duration=body.duration,
        )
        return _png_response(overlay)

    # ------------------------------------------------------------------
    # audio utilities
    # ------------------------------------------------------------------
    @app.post("/api/audio/mix", tags=["audio"])
    def mix_project_audio(body: AudioMixRequest) -> FileResponse:
        if body.project_id:
            project = _get_project(body.project_id)
        elif body.project:
            project = Project.from_dict(body.project)
            prepare_project(project, probe_files=False)
        else:
            raise HTTPException(status_code=400, detail="provide 'project_id' or 'project'")
        filename = Path(body.filename or "mix.wav").name
        target = _unique_output(OUTPUT / "mixes", filename)
        result = mix_audio(project, str(target))
        if result is None:
            raise HTTPException(status_code=400, detail="project has no audible audio")
        return FileResponse(str(target), media_type="audio/wav", filename=target.name)

    @app.post("/api/audio/silence", tags=["audio"])
    def find_silence(body: SilenceRequest) -> dict[str, Any]:
        path = _media_path(body.path)
        ranges = detect_silence(
            str(path),
            threshold_db=body.threshold_db,
            min_silence=body.min_silence,
            samples=body.samples,
        )
        return {"path": str(path), "ranges": [list(item) for item in ranges]}

    # ------------------------------------------------------------------
    # vision
    # ------------------------------------------------------------------
    @app.post("/api/vision/detect", tags=["vision"])
    def vision_detect(body: VisionRequest) -> dict[str, Any]:
        frame = _input_frame(body.path, body.image_base64, body.time)
        persons = detect_persons(frame, confidence=body.confidence)
        faces = detect_faces(frame)
        return {
            "width": int(frame.shape[1]),
            "height": int(frame.shape[0]),
            "persons": [person.to_dict() for person in persons],
            "faces": [list(face) for face in faces],
        }

    @app.post("/api/vision/segment", tags=["vision"])
    def vision_segment(body: VisionRequest) -> Response:
        frame = _input_frame(body.path, body.image_base64, body.time)
        point = tuple(body.point) if body.point and len(body.point) == 2 else None
        mask = person_mask(frame, point=point, index=body.index)
        if mask is None:
            raise HTTPException(status_code=422, detail="no person mask could be computed")
        return _png_response((np.clip(mask, 0, 1) * 255).astype(np.uint8))

    @app.post("/api/vision/select", tags=["vision"])
    def vision_select(body: VisionRequest) -> dict[str, Any]:
        frame = _input_frame(body.path, body.image_base64, body.time)
        point = tuple(body.point) if body.point and len(body.point) == 2 else None
        person = select_person(frame, point, index=body.index)
        if person is None:
            raise HTTPException(status_code=422, detail="no person detected")
        return person.to_dict()

    @app.post("/api/vision/face", tags=["vision"])
    def vision_face(body: VisionRequest) -> dict[str, Any]:
        frame = _input_frame(body.path, body.image_base64, body.time)
        faces = detect_faces(frame)
        return {"faces": [list(face) for face in faces], "largest": list(max(faces, key=lambda b: b[2] * b[3])) if faces else None}

    return app


app = create_app()
