"""Tk desktop front end built from small feature mixins.

Importing this package loads Tkinter.  The headless backend lives in
``videomerger`` and does not import this package.
"""
from __future__ import annotations

from .app import VideoMergerStudio, main

__all__ = ["VideoMergerStudio", "main"]
