from __future__ import annotations

import ast
from pathlib import Path

source = Path("gui_merger.py").read_text(encoding="utf-8")
tree = ast.parse(source)
for node in tree.body:
    if isinstance(node, ast.ClassDef):
        print("class", node.name, node.lineno, node.end_lineno)
        for item in node.body:
            if isinstance(item, (ast.Assign, ast.AnnAssign)):
                targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                names = []
                for target in targets:
                    names.append(ast.unparse(target))
                text = " = ".join(names)
                value = item.value
                if isinstance(value, (ast.Constant, ast.List, ast.Tuple, ast.Dict)):
                    rendered = ast.unparse(value)
                    if len(rendered) > 120:
                        rendered = rendered[:117] + "..."
                else:
                    rendered = f"<{type(value).__name__}>"
                print(f"  {item.lineno:5d}-{item.end_lineno:5d} {text} = {rendered}")
