from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from videomerger.api.app import app
from videomerger.services import STORE


@pytest.fixture()
def client():
    STORE.clear()
    with TestClient(app) as test_client:
        yield test_client


def _create_project(client: TestClient) -> str:
    response = client.post(
        "/api/projects",
        json={"name": "api test", "format": "landscape", "width": 160, "height": 120, "fps": 12},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_health_and_catalogues(client):
    assert client.get("/health").json()["status"] == "ok"
    effects = client.get("/api/effects").json()["effects"]
    assert len(effects) == 11
    capabilities = client.get("/api/capabilities")
    assert capabilities.status_code == 200
    assert "title_themes" in capabilities.json()


def test_project_crud_and_timeline(client, sample_video):
    project_id = _create_project(client)
    response = client.post(
        f"/api/projects/{project_id}/clips",
        json={"clip": {"kind": "video", "path": sample_video, "name": "a"}},
    )
    assert response.status_code == 201, response.text
    clip_id = response.json()["clip"]["id"]

    timeline = client.get(f"/api/projects/{project_id}/timeline").json()
    assert timeline["clips"][0]["id"] == clip_id
    assert timeline["duration"] > 0

    patch = client.patch(
        f"/api/projects/{project_id}/clips/{clip_id}",
        json={"volume": 0.2, "transform": {"scale": 1.3}},
    )
    assert patch.status_code == 200
    assert patch.json()["clip"]["volume"] == 0.2

    split = client.post(
        f"/api/projects/{project_id}/clips/{clip_id}/split",
        json={"time": 0.5},
    )
    assert split.status_code == 200, split.text
    assert split.json()["right"]["trim_start"] == 0.5

    assert client.post(f"/api/projects/{project_id}/undo").status_code == 200
    assert client.post(f"/api/projects/{project_id}/redo").status_code == 200


def test_preview_titles_and_effect_apply(client, sample_video):
    project_id = _create_project(client)
    client.post(
        f"/api/projects/{project_id}/clips",
        json={"clip": {"kind": "video", "path": sample_video, "name": "a"}},
    )
    preview = client.get(f"/api/projects/{project_id}/preview.png", params={"time": 0.2})
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"

    card = client.post("/api/titles/card", json={"main_text": "HI", "width": 160, "height": 120})
    assert card.status_code == 200
    assert card.content[:8] == b"\x89PNG\r\n\x1a\n"

    effect = client.post(
        "/api/effects/film_burn/apply",
        json={"path": sample_video, "time": 0.2, "params": {"intensity": 0.4}},
    )
    assert effect.status_code == 200
    assert effect.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_upload_and_add_media(client, sample_video):
    with Path(sample_video).open("rb") as handle:
        upload = client.post(
            "/api/media/upload",
            files={"file": ("sample.mp4", handle, "video/mp4")},
        )
    assert upload.status_code == 200, upload.text
    assert upload.json()["has_video"] is True

    project_id = _create_project(client)
    with Path(sample_video).open("rb") as handle:
        response = client.post(
            f"/api/projects/{project_id}/media",
            files={"file": ("sample.mp4", handle, "video/mp4")},
        )
    assert response.status_code == 201, response.text
    assert response.json()["clip"]["kind"] == "video"


def test_export_job_and_download(client, sample_video):
    project_id = _create_project(client)
    response = client.post(
        f"/api/projects/{project_id}/clips",
        json={"clip": {"kind": "video", "path": sample_video, "name": "a"}},
    )
    clip_id = response.json()["clip"]["id"]
    client.patch(f"/api/projects/{project_id}/clips/{clip_id}", json={"trim_end": 0.5})
    client.post(f"/api/projects/{project_id}/reflow", json={"start": 0.0})

    export = client.post(
        f"/api/projects/{project_id}/export",
        json={"output_name": "api_test.mp4", "fps": 8},
    )
    assert export.status_code == 202, export.text
    job_id = export.json()["id"]

    status = "queued"
    for _ in range(80):
        data = client.get(f"/api/jobs/{job_id}").json()
        status = data["status"]
        if status in {"done", "error", "cancelled"}:
            break
        time.sleep(0.25)
    assert status == "done", data
    download = client.get(f"/api/jobs/{job_id}/download")
    assert download.status_code == 200
    assert len(download.content) > 0
