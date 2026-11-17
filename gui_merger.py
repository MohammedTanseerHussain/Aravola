"""Desktop launcher for the Ultimate NLE Studio Pro editor.

The implementation lives in :mod:`videomerger.gui` as small feature mixins;
this file exists only so ``python gui_merger.py`` keeps working.
"""
from __future__ import annotations

from videomerger.gui import VideoMergerStudio, main

__all__ = ["VideoMergerStudio", "main"]


if __name__ == "__main__":
    main()
