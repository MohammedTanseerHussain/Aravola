"""One-off refactor helper.

Pulls the self-contained visual-effect methods out of the legacy
``gui_merger.py`` monolith and writes them as plain, importable functions in
``videomerger/effects``. Kept in the repo so the extraction is reproducible
and the legacy GUI can be compared against the new library.

Run from the project root:

    python tools/refactor/extract_effects.py
"""
from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "gui_merger.py"
OUT = ROOT / "videomerger" / "effects"

HEADER = '''"""{doc}"""
from __future__ import annotations

import numpy as np
import cv2
import PIL.Image
from PIL import ImageDraw, ImageFont, ImageFilter


'''


def _class_methods(tree: ast.Module) -> dict[str, ast.AST]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "VideoMergerStudio":
            return {
                child.name: child
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise SystemExit("VideoMergerStudio not found")


def _class_constants(tree: ast.Module) -> dict[str, ast.AST]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "VideoMergerStudio":
            out = {}
            for child in node.body:
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name):
                            out[target.id] = child
                elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                    out[child.target.id] = child
            return out
    return {}


def _src(source: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source, node)
    if segment is None:
        raise SystemExit(f"Could not extract source for {node}")
    lines = segment.splitlines()
    # ast.get_source_segment starts at the token itself, so the first line has
    # no indentation while the following lines keep the original class-body
    # indentation. Strip that leading offset from the continuation lines.
    offset = getattr(node, "col_offset", 0)
    if offset:
        prefix = " " * offset
        for i in range(1, len(lines)):
            if lines[i].startswith(prefix):
                lines[i] = lines[i][offset:]
    return textwrap.dedent("\n".join(lines))


def _strip_self_parameter(source: str, name: str) -> str:
    source = re.sub(
        rf"def\s+{re.escape(name)}\s*\(\s*self\s*,\s*",
        f"def {name}(",
        source,
    )
    source = re.sub(
        rf"def\s+{re.escape(name)}\s*\(\s*self\s*\)",
        f"def {name}()",
        source,
    )
    return source


def _rename_definition(source: str, old: str, new: str) -> str:
    return re.sub(rf"def\s+{re.escape(old)}\s*\(", f"def {new}(", source)


def _build(
    source: str,
    methods: dict[str, ast.AST],
    constants: dict[str, ast.AST],
    *,
    doc: str,
    method_specs: list[tuple[str, str]],
    constant_names: list[str],
    replacements: dict[str, str],
) -> str:
    chunks = [HEADER.format(doc=doc)]
    for const_name in constant_names:
        chunks.append(_src(source, constants[const_name]) + "\n\n")
    for old_name, new_name in method_specs:
        text = _src(source, methods[old_name])
        text = _strip_self_parameter(text, old_name)
        if old_name != new_name:
            text = _rename_definition(text, old_name, new_name)
        for old, new in replacements.items():
            text = text.replace(old, new)
        if re.search(r"\bself\b", text):
            leftover = sorted(set(re.findall(r"self\.[A-Za-z_][A-Za-z0-9_]*", text)))
            raise SystemExit(
                f"{old_name}: unresolved self references: {leftover}"
            )
        chunks.append(text.rstrip() + "\n\n")
    return "".join(chunks).rstrip() + "\n"


def write_module(filename: str, content: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({len(content.splitlines())} lines)")


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = _class_methods(tree)
    constants = _class_constants(tree)

    write_module(
        "color.py",
        _build(
            source,
            methods,
            constants,
            doc="Colour grading filters for RGB frames (legacy parity).",
            method_specs=[("apply_color_filter", "apply_color_filter")],
            constant_names=[],
            replacements={},
        ),
    )

    write_module(
        "film_burn.py",
        _build(
            source,
            methods,
            constants,
            doc="Film-burn / scorching light-leak overlay.",
            method_specs=[("_create_film_burn_effect", "create_film_burn")],
            constant_names=[],
            replacements={},
        ),
    )

    write_module(
        "sun_glare.py",
        _build(
            source,
            methods,
            constants,
            doc="Warm cinematic sun glare with lens-flare chain.",
            method_specs=[("_create_sun_glare_effect", "create_sun_glare")],
            constant_names=["_SUN_GLARE_POSITIONS"],
            replacements={
                "self._SUN_GLARE_POSITIONS": "_SUN_GLARE_POSITIONS",
            },
        ),
    )

    write_module(
        "x_flare.py",
        _build(
            source,
            methods,
            constants,
            doc="Anamorphic X-shaped cross flare.",
            method_specs=[("_create_x_flare_effect", "create_x_flare")],
            constant_names=["_X_FLARE_POSITIONS", "_X_FLARE_COLORS"],
            replacements={
                "self._X_FLARE_POSITIONS": "_X_FLARE_POSITIONS",
                "self._X_FLARE_COLORS": "_X_FLARE_COLORS",
            },
        ),
    )

    write_module(
        "light_flash.py",
        _build(
            source,
            methods,
            constants,
            doc="Paparazzi / camera-flash X-star bursts.",
            method_specs=[
                ("_light_flash_pseudo_random", "_light_flash_pseudo_random"),
                ("_create_light_flash_effect", "create_light_flash"),
            ],
            constant_names=["_LIGHT_FLASH_POSITIONS", "_LIGHT_FLASH_COLORS"],
            replacements={
                "self._LIGHT_FLASH_POSITIONS": "_LIGHT_FLASH_POSITIONS",
                "self._LIGHT_FLASH_COLORS": "_LIGHT_FLASH_COLORS",
                "self._light_flash_pseudo_random": "_light_flash_pseudo_random",
            },
        ),
    )

    write_module(
        "canopy.py",
        _build(
            source,
            methods,
            constants,
            doc="Fog + volumetric god-ray canopy overlay.",
            method_specs=[("_create_canopy_effect", "create_canopy")],
            constant_names=["_CANOPY_LIGHT_DIRS"],
            replacements={
                "self._CANOPY_LIGHT_DIRS": "_CANOPY_LIGHT_DIRS",
            },
        ),
    )

    write_module(
        "ken_burns.py",
        _build(
            source,
            methods,
            constants,
            doc="Ken Burns (zoom / pan) applied to an RGB frame.",
            method_specs=[
                ("_apply_kenburns_zoom_numpy", "apply_kenburns"),
            ],
            constant_names=[],
            replacements={},
        ),
    )


if __name__ == "__main__":
    main()
