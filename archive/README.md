# Archive

This directory preserves the code and assets that were replaced during the
modularisation. Nothing here is imported by the running application or by the
active pytest suite.

## `legacy/`

| Path | What it is |
| --- | --- |
| `gui_merger_monolith.py` | Original 14,967-line desktop application before it was split into `videomerger/gui/` |
| `audio_legacy_gui.py` | Earlier standalone audio GUI prototype |
| `main_legacy_cli.py`, `src_legacy_cli/` | Old CLI that merged videos with crossfades |
| `tests/test_merger_legacy_cli.py` | Test for the archived CLI |
| `root-assets/` | Old root-level accessory PNGs; runtime now uses `assets/accessories/`. Duplicate root model files were removed after byte comparison against `assets/models/`. |

## `tools/`

One-off scripts used to split the monolith and extract the accessory artwork.
They are kept for audit and reproducibility, but assume the original monolith
and hard-coded source-image paths. Do not run them against the current tree
without adjusting those paths.

The canonical runtime assets live in `assets/models/` and
`assets/accessories/`.
