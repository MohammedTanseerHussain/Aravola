# VideoMerger architecture

VideoMerger ships two front ends over one headless feature library:

```powershell
python gui_merger.py     # desktop editor (thin launcher)
python run_api.py        # FastAPI backend
```

The desktop editor is composed from small feature mixins in
`videomerger/gui/`. `gui_merger.py` now only imports and launches it, so both
front ends share the same repository layout, configuration and assets while the
headless `videomerger/` package remains independently importable.

---

## 1. Design principles

- **One feature, one module.** Each effect, the title renderer, media probing,
  vision helpers, audio mixing and the exporter live in their own file.
- **Pure functions at the bottom.** Effects take a NumPy frame and return a
  NumPy frame. They do not know about Tkinter, HTTP, projects or MoviePy.
- **One shared look pipeline.** Preview and export both call
  `videomerger.render.frame.apply_clip_look()`, so the still preview and the
  final MP4 apply colours, effects, transforms and captions in the same order.
- **Thin entry points.** `gui_merger.py` and `run_api.py` only launch their
  packages. The implementation stays in importable, testable modules.
- **Lazy heavy imports.** MediaPipe, Ultralytics/YOLO, MoviePy and Pygame are
  imported only by the modules that need them. Importing `videomerger` does not
  open models or start threads.
- **Legacy compatibility.** `Clip.from_legacy_dict()` and the `extra` dictionary
  accept the old GUI field names (`type`, `clip_start`, `tl_start`, `trans`,
  `effect_*_enabled`, etc.), so GUI project data can be passed to the backend.

---

## 2. Running

### Requirements

- Python 3.11 is the tested interpreter (the local virtualenv is `.venvvideo/`).
- `requirements.txt` is the shared runtime: MoviePy, MediaPipe, NumPy, OpenCV,
  Pillow and pytest.
- `requirements-api.txt` adds FastAPI, uvicorn, multipart and httpx.
- `requirements-vision.txt` adds Ultralytics/YOLO. It pulls in Torch and is
  optional; the backend and GUI both fall back to MediaPipe/GrabCut without it.

```powershell
python -m pip install -r requirements.txt
# API work:
python -m pip install -r requirements-api.txt
# Optional YOLO tracking:
python -m pip install -r requirements-vision.txt
```

### Desktop GUI

```powershell
python gui_merger.py
# equivalent module entry point:
python -m videomerger.gui
```

The launcher imports `videomerger.gui.main()`, which creates the Tk root and
composes `VideoMergerStudio` from its feature mixins.

### API

```powershell
python run_api.py
# or: python run_api.py --host 0.0.0.0 --port 8000 --reload
```

- Interactive docs: <http://127.0.0.1:8000/docs>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>
- Health checks: `GET /health`, `GET /api/health`
- Capability report: `GET /api/capabilities`

`python -m videomerger` is an alias for `python run_api.py`.

### Tests

```powershell
python -m pytest -q
```

`pytest.ini` limits collection to `tests/` and adds the repository root to the
import path, so archived scripts under `archive/` are not collected.

The suite covers models/timeline maths, all 11 effects, media probing and
thumbnails, audio mixing, titles, preview rendering, a real MP4 export, project
undo/redo, and the API (including an asynchronous export job and download).

The legacy CLI test and the original monolithic GUI files are kept under
`archive/legacy/` for reference; they are not part of the active test suite.

---

## 3. Package layout

### Headless package

```
videomerger/
├── __init__.py              Public re-exports and __version__
├── __main__.py              python -m videomerger -> run_api.py
├── config.py                Root paths, model/accessory lookup, ffmpeg lookup
├── models.py                Project, Clip, AudioTrack, Transform
├── media.py                 Probe, frame reader, thumbnail, filmstrip, waveform,
│                            ffmpeg metadata fallback, audio extraction
├── titles.py                Title cards, lower thirds, plain-text captions
├── audio.py                 Gain envelopes, mute regions, mixdown, silence scan
├── effects/
│   ├── __init__.py          Effect registry, metadata, apply_effect()
│   ├── color.py             Colour grading / grain / scratches
│   ├── film_burn.py         Animated film burn
│   ├── sun_glare.py         Sun glare variations
│   ├── x_flare.py           Anamorphic X flare
│   ├── light_flash.py       Flash / paparazzi bursts
│   ├── canopy.py            Fog and volumetric rays
│   ├── ken_burns.py         Zoom / pan motion
│   ├── gold_outline.py      Glowing subject outline and aura variants
│   ├── thug_life.py         Glasses + chain accessories
│   ├── three_d_text.py      Extruded 3D text
│   └── motion_track.py      Tracking arrow and name label
├── vision/
│   ├── __init__.py
│   └── segmentation.py      MediaPipe, YOLO, GrabCut, Haar faces and tracking
├── render/
│   ├── __init__.py
│   ├── frame.py             Shared frame pipeline, FrameRenderer, transitions
│   └── export.py            MoviePy export, progress/cancel, audio mix
├── services/
│   ├── __init__.py
│   ├── projects.py          In-memory project store, undo/redo, edit helpers
│   └── jobs.py              Background export jobs and cancellation
└── api/
    ├── app.py               FastAPI app, all HTTP routes
    └── schemas.py           Pydantic request bodies
```

### Desktop package

`videomerger/gui/` contains 30 feature mixins plus three shared modules. The
legacy `VideoMergerStudio` class was split mechanically so method bodies and
widget construction stay as close to the original as possible.

```
videomerger/gui/
├── __init__.py              Public exports
├── __main__.py              python -m videomerger.gui
├── app.py                   Composed VideoMergerStudio + main()
├── runtime.py               Shared imports, palette, Tk helpers, lazy loaders
├── constants.py             GuiConstants: timeline sizing, effect palettes
├── core.py                  Lifecycle, undo/redo, clip cache, navigation
├── shell.py                 Window, toolbar and panel construction
├── media.py                 Import, clip creation, templates and clip edits
├── audio.py                 BGM tracks, envelopes and speech easing
├── audio_render.py          Audio cutting and preview mix construction
├── playback.py              Playback transport and preview scheduling
├── preview.py               Full preview and clip-frame composition
├── transitions.py           Preview and export transition blending
├── inspector.py             Selected-clip inspector and clip transforms
├── effects_ui.py            Effect/filter controls and effect-tab refresh
├── effects_settings.py      Effect parameter widget callbacks
├── effects_filters.py       Colour-filter application
├── effects_gold.py          Gold outline, aura and god-ray rendering
├── effects_film.py          Film burn and sun-glare rendering
├── effects_flare.py         X-flare and light-flash rendering
├── effects_canopy.py        Fog and volumetric canopy rendering
├── effects_text3d.py        Extruded 3D-text rendering
├── effects_motion.py        Motion-track arrow and label rendering
├── effects_thug.py          Thug-life glasses, chain and cap rendering
├── text3d_ui.py             3D-text placement, handles and auto-tracking UI
├── tracking_ui.py           Person selection and mask-painting interaction
├── tracking_impl.py         Template matching and subject tracking
├── masks.py                 Mask refinement, keyframes and subject centres
├── timeline.py              Hit-testing, trimming and region actions
├── timeline_drag.py         Pointer dragging, scrubbing and playhead moves
├── timeline_render.py       Filmstrips, waveforms and volume envelopes
├── titles.py                Background generators and lower-third builders
├── title_cards.py           Large animated title-card builder
├── export.py                Validation, background export and progress
└── vision.py                MediaPipe/YOLO setup and mask helpers
```

### Supporting directories

```
assets/models/               Canonical Haar, MediaPipe and YOLO model files
assets/accessories/          Canonical glasses/chain/cap PNGs
assets/reference/            Extracted reference artwork (not used at runtime)
tools/smoke/                 Manual smoke/fuzz scripts; not imported by the app
tests/                       Active pytest suite
output/                      Exports, previews and API mixes (generated)
uploads/                     Uploaded media (generated)
archive/legacy/              Original monolith, CLI package and legacy tests
archive/tools/               One-off refactoring and asset-extraction scripts
```

All runtime model and accessory paths resolve through `videomerger/config.py`
and point at `assets/`. Duplicate root-level model files were removed after
verifying byte-identical copies in `assets/models/`; legacy root-level
accessory PNGs are preserved under `archive/legacy/root-assets/`.

---

## 4. Data model

`videomerger.models` defines the complete edit as plain dataclasses. They
serialise to JSON with `to_dict()` and rebuild with `from_dict()`, which is what
the API sends and stores.

| Type | Important fields |
| --- | --- |
| `Project` | `id`, `name`, `format` (`landscape`/`portrait`), `width`, `height`, `fps`, `smart_fill`, `auto_rotate`, `clips`, `audio_tracks` |
| `Clip` | `id`, `kind` (`video`/`image`/`title`/`placeholder`), `path`, `timeline_start`, `trim_start`, `trim_end`, `speed`, `volume`, `muted`, `transform`, `transition`, `transition_duration`, `text`/`text_start`/`text_end`, `title`, `filter`, `effects`, `extra` |
| `Transform` | `scale`, `opacity`, `x`, `y`, `rotation`, `flip_h`, `flip_v` |
| `AudioTrack` | `path`, `volume`, `start_offset`, `trim_start`, `trim_end`, `speed`, `muted`, `envelope`, `mute_regions`, `pt_gains`, `ease_mode` |

Timeline helpers:

- `Clip.effective_duration()` applies trim and speed.
- `Clip.local_time(absolute)` converts timeline time to source time.
- `Project.reflow()` lays clips back-to-back from a start time.
- `Project.split_clip()` splits video by source trim and title/image by
  duration, producing two independently editable clips.
- `Project.total_duration()` includes both video and audio extents.

---

## 5. Feature map

### Project and timeline editing

| Feature | Library | API |
| --- | --- | --- |
| Create / list / get / replace / patch / delete project | `services/projects.py::ProjectStore` | `POST/GET/PUT/PATCH/DELETE /api/projects[...]` |
| Duplicate project | `ProjectStore.duplicate` | `POST /api/projects/{id}/duplicate` |
| Timeline view | `Project.to_dict`, `total_duration`, `timeline_end` | `GET /api/projects/{id}/timeline` |
| Add clip / add uploaded media | `ProjectStore.add_clip`, `media.probe` | `POST /api/projects/{id}/clips`, `POST /api/projects/{id}/media` |
| Patch clip (trim, speed, transform, effects, title, text) | `ProjectStore.update_clip` | `PATCH /api/projects/{id}/clips/{clip_id}` |
| Delete / reorder / split clip | `ProjectStore.remove_clip`, `move_clip`, `split_clip` | `DELETE`, `POST .../reorder`, `POST .../split` |
| Reflow timeline | `Project.reflow` | `POST /api/projects/{id}/reflow` |
| Undo / redo | `ProjectStore.undo` / `redo` | `POST /api/projects/{id}/undo`, `/redo` |
| Manual history snapshot | `ProjectStore.save_state` | `POST /api/projects/{id}/snapshot` |
| Add / patch / delete audio track | `ProjectStore.add_audio`, `update_audio`, `remove_audio` | `/api/projects/{id}/audio...` |
| Attach effect slot to a clip | `ProjectStore.update_clip` | `PUT /api/projects/{id}/clips/{clip_id}/effects/{effect_id}` |
| Remove effect slot | `ProjectStore.update_clip` | `DELETE /api/projects/{id}/clips/{clip_id}/effects/{effect_id}` |

### Media handling

| Feature | Library | API |
| --- | --- | --- |
| Probe video/audio/image metadata | `media.probe` (ffprobe, `ffmpeg -i` fallback, OpenCV fallback) | `POST /api/media/probe`, `GET /api/media/probe`, `POST /api/media/upload` |
| Read one frame | `media.read_frame`, `media.VideoFrameReader` | `GET /api/media/frame` |
| Thumbnail | `media.thumbnail` | `GET /api/media/thumbnail` |
| Filmstrip | `media.filmstrip` | `GET /api/media/filmstrip` |
| Audio waveform samples | `media.waveform_samples` | `GET /api/media/waveform` |
| Extract audio to WAV | `media.extract_audio` | used internally; available as a library call |

### Effects

Every effect is available as a library call (`videomerger.effects.apply_effect`)
and through one HTTP route. Parameters and metadata are returned by
`GET /api/effects` and `GET /api/effects/{effect_id}`.

| Effect id | Module | Notes |
| --- | --- | --- |
| `color_filter` | `effects/color.py` | 10 grading presets; deterministic grain/scratch seeds from `time` |
| `film_burn` | `effects/film_burn.py` | Animated burn edge |
| `sun_glare` | `effects/sun_glare.py` | 4 variations, 5 positions |
| `x_flare` | `effects/x_flare.py` | 4 variations, 5 positions |
| `light_flash` | `effects/light_flash.py` | Flash, paparazzi, neon and full-frame styles |
| `canopy` | `effects/canopy.py` | Fog, light shafts and optional person mask |
| `ken_burns` | `effects/ken_burns.py` | Zoom and pan driven by clip time |
| `gold_outline` | `effects/gold_outline.py` | Legacy god-ray/ethereal/divine/brilliance/holy-aura family, selected with `variation` |
| `thug_life` | `effects/thug_life.py` | Glasses and chain, optional cap; uses a face box |
| `three_d_text` | `effects/three_d_text.py` | Extruded text, optional tracked quad |
| `motion_track` | `effects/motion_track.py` | Arrow + name; uses a bounding box or detects a person |

Call one effect directly:

```python
from videomerger.effects import apply_effect

result = apply_effect(frame, "film_burn", {"intensity": 0.8}, time=1.2)
```

Apply through HTTP:

```bash
curl -X POST http://127.0.0.1:8000/api/effects/film_burn/apply \
  -H "Content-Type: application/json" \
  -d '{"path":"uploads/example.mp4","time":1.2,"params":{"intensity":0.8}}' \
  --output effect.png
```

Effects that need vision data accept a pre-supplied `context` so they are
independently testable:

```python
apply_effect(frame, "gold_outline", {"opacity": 0.8}, context={"mask": mask})
apply_effect(frame, "thug_life", {"style": "realistic"}, context={"face": (x, y, w, h)})
apply_effect(frame, "motion_track", {"name": "SUBJECT"}, context={"bbox": (x, y, w, h)})
```

### Vision

| Feature | Library | API |
| --- | --- | --- |
| Detect people (YOLO, GrabCut fallback) | `vision.detect_persons`, `segment_person` | `POST /api/vision/detect`, `/select` |
| Person mask (MediaPipe, YOLO, GrabCut) | `vision.person_mask`, `grabcut_mask` | `POST /api/vision/segment` |
| Select person by point/index | `vision.select_person` | `POST /api/vision/select` |
| Haar face detection | `vision.detect_faces`, `largest_face` | `POST /api/vision/face`, `/detect` |
| Lightweight tracker | `vision.PersonTracker` | library only |

Models are resolved from `assets/models/`. The YOLO path is optional: install
`requirements-vision.txt`; without it the GrabCut/MediaPipe fallbacks are used.

### Titles and text

| Feature | Library | API |
| --- | --- | --- |
| Animated title card (4 themes) | `titles.render_title_card` | `POST /api/titles/card` |
| Lower third (4 styles) | `titles.render_lower_third`, `composite_lower_third` | `POST /api/titles/lower-third` |
| Plain caption overlay | `titles.overlay_plain_text` | applied by preview/export for `clip.text` |

Themes: Deep Space Stars, Light Speed Burst, Travelling Lens Flare, Aurora.
Styles: Static Aurora Tile (Bracket), News Headline, Purple Designer Box,
Magical Aurora. All four themes are time-animated.

### Preview

| Feature | Library | API |
| --- | --- | --- |
| Single-frame project preview | `render.frame.FrameRenderer` | `POST /api/projects/{id}/preview`, `GET /api/projects/{id}/preview.png` |
| Reusable clip renderer | `render.frame.render_clip_frame` | library only |
| Shared export/preview look | `render.frame.apply_clip_look` | library only |

The renderer resolves the active clip, reads its source frame, fits it to the
canvas (`smart_fill`), applies transform, effect chain, legacy captions and
lower thirds, then blends the previous clip during the transition window.

### Export and jobs

| Feature | Library | API |
| --- | --- | --- |
| Prepare/normalise source metadata | `render.export.prepare_project` | used automatically |
| Export project to MP4 | `render.export.export_project` | `POST /api/projects/{id}/render` (synchronous) |
| Background export with progress | `services.jobs.JobManager` | `POST /api/projects/{id}/export` (202) |
| Poll / list / cancel / delete jobs | `JobManager` | `/api/jobs...` |
| Download finished export | `Job.to_dict` + `FileResponse` | `GET /api/jobs/{id}/download` |

The exporter:

- opens video with `audio=False` and mixes audio separately (legacy Windows
  seek-workaround);
- clamps trims inside the real source duration;
- applies speed, reverse and slow-mo zoom marks from `clip.extra`;
- applies `crossfadein` from black for non-`Hard Cut` transitions, matching the
  preview renderer;
- forwards progress through a proglog-compatible logger and checks a cancel
  event;
- closes every MoviePy clip/reader in a `finally` block.

### Audio

| Feature | Library | API |
| --- | --- | --- |
| Volume, envelope and per-point gains | `audio._apply_track_gain` | clip/audio patch fields |
| Mute regions | `audio._apply_track_gain` | `mute_regions` on audio track |
| Full mixdown to WAV | `audio.mix_audio` | `POST /api/audio/mix` |
| Audio mix for export | `audio.build_audio_mix` | used by `export_project` |
| Silence detection | `audio.detect_silence` | `POST /api/audio/silence` |

Audio layers are zeroed outside their own time range before being composed;
MoviePy otherwise asks a late-starting reader for negative timestamps.

---

## 6. Desktop GUI architecture

`gui_merger.py` is a compatibility launcher:

```python
from videomerger.gui import VideoMergerStudio, main
```

`videomerger/gui/app.py` declares `VideoMergerStudio` as the composition of the
feature mixins. Mixin order matters only where names overlap; the extraction
kept Python's original override semantics (the later `_apply_gold_glow` and
`_apply_gold_halo` definitions win, exactly as they did in the monolith). All
258 unique legacy methods are present on the composed class.

### Shared runtime

`videomerger/gui/runtime.py` owns everything the mixins have in common:

- standard-library, NumPy, OpenCV, Pillow and Tk imports;
- the dark-studio colour palette `C`;
- `Tooltip`, `icon_btn`, `create_scroll_canvas` and
  `extract_waveform_samples`;
- MoviePy/Pygame lazy loading through `_ensure_moviepy()` and
  `_ensure_pygame()`;
- `_TkExportProgressLogger`, which routes MoviePy's progress back to Tk.

Feature modules use `from .runtime import *`. Because Python resolves globals
through the defining module, the lazy loaders call `_sync_lazy_globals()` after
loading MoviePy/Pygame so every GUI module sees the real objects rather than
the initial `None` placeholders.

### Mixin responsibilities

| Area | Modules |
| --- | --- |
| Lifecycle and layout | `core`, `shell` |
| Media, audio and playback | `media`, `audio`, `audio_render`, `playback`, `preview`, `transitions`, `inspector` |
| Effect controls | `effects_ui`, `effects_settings` |
| Effect rendering | `effects_filters`, `effects_gold`, `effects_film`, `effects_flare`, `effects_canopy`, `effects_text3d`, `effects_motion`, `effects_thug` |
| Vision and tracking | `vision`, `tracking_impl`, `tracking_ui`, `masks`, `text3d_ui` |
| Timeline | `timeline`, `timeline_drag`, `timeline_render` |
| Titles and export | `titles`, `title_cards`, `export` |

`constants.py` supplies `GuiConstants`, mixed in last. It holds timeline
dimensions, transition duration, effect variation labels, colour palettes and
the timeline/position tables used by the effect modules.

### GUI assets

The thug-life effect loads real PNG files from `assets/accessories/` through
`EffectsThugMixin._load_thug_asset()` instead of decoding base64 blobs embedded
in the class. `VisionMixin._init_mediapipe()` and `_init_yolo()` resolve their
models from `videomerger.config.SEGMENTER_MODEL` and `YOLO_MODEL`, which point
at `assets/models/`.

### Adding or changing a GUI feature

1. Put the behaviour in the mixin that owns the area, or add a new module with
   one mixin class.
2. Import shared names from `.runtime`; call `_ensure_moviepy()` or
   `_ensure_pygame()` before using lazy objects.
3. If you add a new mixin module, add it to the imports and base-class list in
   `videomerger/gui/app.py`.
4. Keep shared tables in `constants.py` rather than duplicating them.
5. Run `python -m compileall -q videomerger gui_merger.py` and launch
   `python gui_merger.py` for a visual smoke test.

---

## 7. Legacy GUI compatibility

Projects that originated in the GUI can still be loaded by the headless model:

- `Clip.from_legacy_dict()` maps `type`, `clip_start`, `clip_end`, `tl_start`,
  `trans`, `x_offset`, `y_offset`, filter fields and unknown fields to the new
  model (unknown fields go to `Clip.extra`).
- `render.frame._effect_items()` translates legacy `effect_*_enabled` flags and
  `filter` dictionaries into the registry's effect parameters, so old project
  dictionaries preview and export correctly.
- `Project.format` uses the same `landscape`/`portrait` presets
  (1920x1080 / 1080x1920).

The original monolithic `gui_merger.py`, `audio.py`, CLI `main.py`/`src/`, old
root artwork and the legacy CLI test are preserved under `archive/legacy/`.
`archive/tools/` keeps the one-off extraction/refactoring scripts for audit;
neither archive is imported by the running application.

---

## 8. Environment notes

- Python 3.11 is the tested interpreter (`.venvvideo`).
- `ffprobe` is optional. `media.probe` falls back to `ffmpeg -i`, then OpenCV.
- `ffmpeg` is resolved from `FFMPEG_BINARY`, `PATH`, common install paths, and
  finally MoviePy's bundled imageio-ffmpeg binary.
- The GUI uses ImageMagick only for MoviePy `TextClip` paths; the new renderer
  draws text with Pillow.
- `output/` and `uploads/` are created automatically by `videomerger.config`.

---

## 9. Known limits / sensible next steps

- `ProjectStore` is in memory. Restarting the API loses projects; swap it for a
  database-backed repository without touching the renderer or effects.
- `JobManager` defaults to one export worker. Increase `max_workers` for
  multi-user deployments.
- The exporter supports `Hard Cut` and fade/crossfade transitions. The legacy
  GUI's additional transition styles, audio ease presets and some
  GUI-only convenience dialogs are not all exposed through the API yet.
- Preview/export support video, image, title and placeholder clips. The legacy
  GUI's template/apply-template workflow is a candidate for a future
  `services/templates.py` module.
- API authentication, persistent storage and upload quotas are deployment
  concerns and are deliberately not built into the feature libraries.
