"""Start the headless VideoMerger API.

    python run_api.py
    python run_api.py --host 0.0.0.0 --port 8000 --reload

The desktop GUI is separate: launch it with ``python gui_merger.py`` or
``python -m videomerger.gui``.
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="VideoMerger headless API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print(
            "FastAPI/uvicorn are not installed.\n"
            "Run:  pip install -r requirements-api.txt",
            file=sys.stderr,
        )
        return 1

    if args.reload:
        uvicorn.run("videomerger.api.app:app", host=args.host, port=args.port, reload=True)
    else:
        uvicorn.run(
            "videomerger.api.app:app",
            host=args.host,
            port=args.port,
            workers=max(1, args.workers),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
