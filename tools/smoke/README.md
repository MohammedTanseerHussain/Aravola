# Manual smoke scripts

These scripts are developer aids, not part of the automated test suite. Run
them from the repository root with the project importable.

Suggested order:

```powershell
python -m pip install -r requirements-api.txt
python tools/smoke/export_smoke.py      # creates output/src_a.mp4 + src_b.mp4
python tools/smoke/audio_check.py       # creates output/audio_check.mp4
python tools/smoke/audio_smoke.py
python tools/smoke/preview_smoke.py
python tools/smoke/effects_debug.py
python tools/smoke/fuzz_small_frames.py
python tools/smoke/api_smoke.py         # uses output/src_a.mp4
```

`api_export_debug.py` is a small direct-export repro helper. Generated files
land under `output/`, which is ignored by git.
