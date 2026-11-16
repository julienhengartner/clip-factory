"""Cast reference sheet: builds every character from the bible and renders a line-up.

    blender -b --factory-startup -P blender/reference_sheet.py -- <out.png> [width height]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "blender"))

from bobbington.bible import CAST, PALETTE  # noqa: E402
import characters  # noqa: E402
import scene_kit  # noqa: E402


def main(argv: list[str]) -> None:
    out = (Path(argv[0]) if argv else ROOT / "docs" / "bible" / "cast_lineup.jpg").resolve()
    w, h = (int(argv[1]), int(argv[2])) if len(argv) >= 3 else (1920, 1080)
    scene_kit.reset_scene()
    order = ["margaret", "reginald", "winston", "brenda", "arthur", "nigel"]
    spacing = 0.95
    for i, cid in enumerate(order):
        x = (i - (len(order) - 1) / 2) * spacing
        c = characters.build_character(cid, CAST[cid], PALETTE, location=(x, 0, 0))
        scene_kit.label(CAST[cid]["name"], (x, -0.45, 0.02), size=0.07)
    scene_kit.studio_backdrop()
    scene_kit.three_point_lights(target=(0, 0, 1.0))
    scene_kit.camera(location=(0, -7.0, 1.25), target=(0, 0, 0.95), lens=40)
    scene_kit.render_settings(w, h, fps=24, samples=16)
    t = time.time()
    scene_kit.render_still(out)
    print(f"RENDER_SECONDS={time.time() - t:.2f}")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
