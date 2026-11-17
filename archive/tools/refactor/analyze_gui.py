"""Inventory gui_merger.py so it can be split into feature modules."""
from __future__ import annotations

import ast
import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "gui_merger.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    print(f"{path}: {len(source.splitlines())} lines")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            print(f"FUNC {node.name:40s} {node.lineno:5d}-{node.end_lineno:5d}")
        elif isinstance(node, ast.ClassDef):
            print(f"CLASS {node.name} {node.lineno}-{node.end_lineno}")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    decorators = ",".join(
                        ast.unparse(d) for d in item.decorator_list
                    )
                    print(
                        f"  {item.name:42s} {item.lineno:5d}-{item.end_lineno:5d}"
                        f"  {decorators}"
                    )
        elif isinstance(node, ast.Assign):
            targets = ", ".join(ast.unparse(t) for t in node.targets)
            if len(targets) > 80:
                targets = targets[:77] + "..."
            print(f"ASSIGN {targets} {node.lineno}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
