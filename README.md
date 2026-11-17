# VideoMerger

Desktop video editor and headless editing backend for Windows. The repository
contains one shared feature library with two front ends:

| Entry point | What it starts |
| --- | --- |
| `python gui_merger.py` | Ultimate NLE Studio Pro desktop editor (Tk) |
| `python run_api.py` | Headless FastAPI backend at `http://127.0.0.1:8000` |

The GUI implementation is split into small feature modules under
`videomerger/gui/`; `gui_merger.py` is only a launcher. The backend under
`videomerger/` is importable on its own and powers the HTTP API.

---

## Quick start

### 1. Install

Python 3.11 is the tested interpreter.

```powershell
python -m pip install -r requirements.txt
```

Optional extras:

```powershell
python -m pip install -r requirements-api.txt    # FastAPI backend
python -m pip install -r requirements-vision.txt # YOLO tracking (pulls in Torch)
```

### 2. Start the desktop editor

```powershell
python gui_merger.py
# equivalent:
python -m videomerger.gui
```

### 3. Start the API

```powershell
python run_api.py
# or: python run_api.py --host 0.0.0.0 --port 8000 --reload
```

- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>
- Health: `GET /health` or `GET /api/health`
- Capabilities: `GET /api/capabilities`

### 4. Run the tests

```powershell
python -m pytest -q
```

`pytest.ini` limits collection to `tests/` and adds the repository root to the
import path, so the archived legacy test is never collected.

The active suite covers the data model, timeline maths, all 11 effects, media
probing, audio, titles, preview rendering, a real MP4 export, undo/redo and the
API including asynchronous export jobs.

---

## Using the API

A typical integration flow is:

1. `POST /api/projects` to create a project.
2. `POST /api/projects/{id}/clips` (or `/media` for uploads) to add clips.
3. `PATCH /api/projects/{id}/clips/{clip_id}` to set trims, transforms,
   transitions, filters or effects.
4. `POST /api/projects/{id}/preview` to render a still, or
   `POST /api/projects/{id}/export` to start a background job.
5. Poll `GET /api/jobs/{job_id}`, then download from
   `GET /api/jobs/{job_id}/download`.

Effects can also be applied directly:

```powershell
curl -X POST http://127.0.0.1:8000/api/effects/film_burn/apply `
  -H "Content-Type: application/json" `
  -d '{"path":"uploads/example.mp4","time":1.2,"params":{"intensity":0.8}}' `
  --output effect.png
```

The backend can be used without HTTP:

```python
from videomerger.models import Clip, Project
from videomerger.render.export import export_project, prepare_project

project = Project(name="demo", width=1920, height=1080, fps=30)
project.add_clip(Clip(kind="video", path="uploads/example.mp4", name="A"))
prepare_project(project)
export_project(project, "output/demo.mp4")
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full feature map, data model,
effects catalog, render pipeline and GUI mixin responsibilities.

---

## Repository layout

```
gui_merger.py            Desktop launcher (thin wrapper)
run_api.py               FastAPI launcher
videomerger/             Headless backend package
videomerger/gui/         Desktop feature mixins and composed application
assets/models/           Canonical Haar, MediaPipe and YOLO models
assets/accessories/      Canonical glasses/chain/cap PNGs
assets/reference/        Extracted reference artwork (not used at runtime)
tests/                   Active pytest suite
tools/smoke/             Manual developer smoke scripts
output/                  Generated exports, previews and mixes
uploads/                 Generated API uploads
archive/legacy/          Original monolith, CLI package and legacy test
archive/tools/           One-off refactoring and asset-extraction scripts
```

`output/` and `uploads/` are created automatically at import time and are
ignored by git.

---

## Desktop GUI notes

- `videomerger/gui/app.py` composes `VideoMergerStudio` from 30 feature mixins:
  lifecycle/layout, media, audio, playback, preview, effects, tracking,
  timeline, titles and export.
- Shared imports, colours, Tk helpers and lazy MoviePy/Pygame loading live in
  `videomerger/gui/runtime.py`.
- Shared timeline sizes and effect palettes live in
  `videomerger/gui/constants.py`.
- The thug-life effect reads PNGs from `assets/accessories/`; vision models are
  resolved through `videomerger/config.py`.
- The original 14,967-line monolith is preserved at
  `archive/legacy/gui_merger_monolith.py` for comparison.

### Adding a GUI feature

1. Put the behaviour in the mixin that owns that area, or add a new module with
   one mixin class.
2. Use `from .runtime import *` and call `_ensure_moviepy()` /
   `_ensure_pygame()` before touching lazy objects.
3. If you add a new mixin, import it and add it to the base-class list in
   `videomerger/gui/app.py`.
4. Keep cross-module tables in `constants.py`.
5. Compile and visually smoke-test:

```powershell
python -m compileall -q videomerger gui_merger.py
python gui_merger.py
```

---

## Assets and archive

All runtime assets are under `assets/`. Duplicate root-level model files were
removed after verifying byte-identical copies in `assets/models/`; the old
root-level accessory PNGs were moved to `archive/legacy/root-assets/` rather
than deleted. `archive/legacy/` also contains the original monolith, the old
`audio.py`, `main.py`, `src/` CLI package and the legacy CLI test.
`archive/tools/` contains the one-off split/extraction scripts used during the
refactor. Nothing under `archive/` is imported by the application or the test
suite.

---

## Environment notes

- Python 3.11 is the tested interpreter.
- `ffmpeg` is resolved from `FFMPEG_BINARY`, `PATH`, common Windows install
  paths, or MoviePy's bundled imageio-ffmpeg binary.
- `ffprobe` is optional; media probing falls back to `ffmpeg -i` and OpenCV.
- YOLO is optional. Without `requirements-vision.txt`, vision code falls back
  to MediaPipe/GrabCut.
- `output/` and `uploads/` contain generated data and should not be committed.
