"""Creates the Blender scene of a city version.

    blender -b --factory-startup -P blender/build_city.py -- build  <version_folder>
    blender -b --factory-startup -P blender/build_city.py -- derive <version_folder> <parent_version_folder>

build  : only for the baseline (v001) – builds the scene from state.json.
derive : opens the PARENT version's scene.blend (reuse, no regeneration) and applies only the story events in
         changes.json. Saves scene.blend, inventory.json and reference renders in the version folder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "blender")]

import city_scene  # noqa: E402
import scene_kit  # noqa: E402


def main(argv: list[str]) -> None:
    mode, folder = argv[0], Path(argv[1]).resolve()
    state = json.loads((folder / "state.json").read_text(encoding="utf-8"))
    if mode == "build":
        scene_kit.reset_scene()
        city_scene.build_state(state)
    elif mode == "derive":
        parent = Path(argv[2]).resolve()
        bpy.ops.wm.open_mainfile(filepath=str(parent / "scene.blend"))
        records = json.loads((folder / "changes.json").read_text(encoding="utf-8"))
        city_scene.apply_changes(records, state, frames=None)
    else:
        raise SystemExit(f"unknown mode {mode}")
    inv = city_scene.inventory()
    (folder / "inventory.json").write_text(json.dumps(inv, indent=1), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / "scene.blend"), compress=True)
    city_scene.render_references(state, folder / "refs")
    print(f"CITY_BUILT mode={mode} objects={inv['count']}")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:])
