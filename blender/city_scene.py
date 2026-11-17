"""Builds Bobbington in Blender from the city state – and nothing else (runs inside Blender 4.5).

Every Blender object carries custom properties city_id / city_group / city_location / city_material, so a
saved scene can always be audited against state.json (inventory). Story events can be applied
- statically (deriving the next version's scene from the previous scene file), or
- from a given frame (inside an episode: before the event the old town is visible, afterwards the new one).
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import bpy

import characters
from scene_kit import look_at

from bobbington.bible import PALETTE

REF_SETTINGS = {"width": 480, "height": 854, "samples": 8}   # identical for every version -> comparable


def city_material(spec: dict) -> bpy.types.Material:
    key = hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:8]
    name = f"city_{spec['name']}_{key}"
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    rgba = characters.colour(spec["colour"], PALETTE)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = spec.get("rough", 0.6)
    bsdf.inputs["Metallic"].default_value = spec.get("metal", 0.0)
    if spec.get("emission"):
        bsdf.inputs["Emission Color"].default_value = rgba
        bsdf.inputs["Emission Strength"].default_value = spec["emission"]
    return m


def _collection(location: str) -> bpy.types.Collection:
    name = f"CITY_{location}"
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def _tag(obj, spec: dict) -> None:
    obj["city_id"] = spec["id"]
    obj["city_group"] = spec["group"]
    obj["city_location"] = spec["location"]
    obj["city_material"] = spec["material"]["name"] if spec.get("material") else ""
    obj.name = spec["id"]
    for c in obj.users_collection:
        c.objects.unlink(obj)
    _collection(spec["location"]).objects.link(obj)


def _apply_condition(obj, spec: dict) -> None:
    cond = spec.get("condition", "intact")
    if cond == "damaged":
        obj.rotation_euler.y += math.radians(6)
        obj.rotation_euler.x += math.radians(3)
        obj["city_condition"] = "damaged"
    elif cond == "under_construction":
        obj.scale = (obj.scale[0], obj.scale[1], obj.scale[2] * 0.55)
        obj["city_condition"] = "under_construction"


def build_object(spec: dict) -> bpy.types.Object:
    k = spec["kind"]
    if k == "light":
        ld = bpy.data.lights.new(spec["id"], "AREA")
        ld.energy, ld.size, ld.color = spec["energy"], spec["size"], spec["color"]
        o = bpy.data.objects.new(spec["id"], ld)
        bpy.context.scene.collection.objects.link(o)
        o.location = spec["loc"]
        look_at(o, spec["target"])
        _tag(o, {**spec, "material": None})
        return o
    if k == "text":
        cu = bpy.data.curves.new(spec["id"], "FONT")
        cu.body = spec["body"]
        cu.size = spec["size"]
        cu.extrude = spec.get("extrude", 0.003)
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        if spec.get("font") and Path(spec["font"]).is_file():
            cu.font = bpy.data.fonts.load(spec["font"], check_existing=True)
        o = bpy.data.objects.new(spec["id"], cu)
        bpy.context.scene.collection.objects.link(o)
        o.location, o.rotation_euler = spec["loc"], spec.get("rot", (math.radians(90), 0, 0))
        o.data.materials.append(city_material({"name": f"text_{spec['colour']}", "colour": spec["colour"], "rough": 0.5}))
        _tag(o, {**spec, "material": {"name": f"text_{spec['colour']}"}})
        return o
    m = city_material(spec["material"])
    if k == "cube":
        o = characters.cube(spec["id"], spec["loc"], spec["scale"], m, bevel=spec.get("bevel", 0.0))
    elif k == "cylinder":
        o = characters.cylinder(spec["id"], spec["loc"], spec["radius"], spec["depth"], m, rot=spec.get("rot", (0, 0, 0)),
                                vertices=spec.get("vertices", 24), scale=spec.get("scale", (1, 1, 1)))
    elif k == "cone":
        o = characters.cone(spec["id"], spec["loc"], spec["r1"], spec["r2"], spec["depth"], m,
                            rot=spec.get("rot", (0, 0, 0)), vertices=spec.get("vertices", 24))
    elif k == "sphere":
        o = characters.sphere(spec["id"], spec["loc"], spec["scale"], m)
    elif k == "torus":
        o = characters.torus(spec["id"], spec["loc"], spec["major"], spec["minor"], m, rot=spec.get("rot", (0, 0, 0)))
    else:
        raise ValueError(f"unknown kind {k}")
    _tag(o, spec)
    _apply_condition(o, spec)
    return o


def set_environment(env: dict) -> None:
    sc = bpy.context.scene
    if not sc.world:
        sc.world = bpy.data.worlds.new("World")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (*env["world"]["colour"], 1)
    bg.inputs["Strength"].default_value = env["world"]["strength"]
    sun = bpy.data.objects.get("CITY_sun")
    if sun is None:
        ld = bpy.data.lights.new("CITY_sun", "SUN")
        sun = bpy.data.objects.new("CITY_sun", ld)
        sc.collection.objects.link(sun)
    sun.data.energy = env["sun"]["energy"]
    sun.data.color = env["sun"]["colour"]
    sun.data.angle = math.radians(5)
    sun.rotation_euler = [math.radians(a) for a in env["sun"]["rotation_deg"]]


def build_state(state: dict) -> None:
    set_environment(state["environment"])
    for spec in state["objects"]:
        build_object(spec)


def city_objects() -> dict[str, list]:
    out: dict[str, list] = {}
    for o in bpy.data.objects:
        if "city_id" in o.keys():
            out.setdefault(o["city_id"], []).append(o)
    return out


def _key_visibility(obj, visible_from: int | None = None, hidden_from: int | None = None) -> None:
    if visible_from is not None:
        obj.hide_render = True
        obj.keyframe_insert("hide_render", frame=0)
        obj.hide_render = False
        obj.keyframe_insert("hide_render", frame=visible_from)
    if hidden_from is not None:
        obj.hide_render = False
        obj.keyframe_insert("hide_render", frame=0)
        obj.hide_render = True
        obj.keyframe_insert("hide_render", frame=hidden_from)


def apply_changes(records: list[dict], new_state: dict, frames: dict[str, int] | None = None) -> None:
    """Applies story events to the open scene. With `frames` ({from_shot: frame}) the change happens on screen
    at that frame (episode render); without, it is permanent (deriving the next version)."""
    by_id = {o["id"]: o for o in new_state["objects"]}
    existing = city_objects()
    for r in records:
        at = frames.get(r.get("from_shot"), 0) if frames is not None else None
        if r["op"] == "add":
            for oid in r["objects"]:
                o = build_object(by_id[oid])
                if at:
                    _key_visibility(o, visible_from=at)
        elif r["op"] == "remove":
            for oid in r["objects"]:
                for o in existing.get(oid, []):
                    if at is not None:
                        _key_visibility(o, hidden_from=at)
                    else:
                        bpy.data.objects.remove(o, do_unlink=True)
        elif r["op"] in ("set_text", "set_condition", "move"):
            for oid in r["objects"]:
                for old in existing.get(oid, []):
                    if at is not None:   # swap old -> new representation at the event frame
                        new = build_object({**by_id[oid], "id": f"{oid}@new"})
                        new["city_id"] = f"{oid}@new"
                        _key_visibility(old, hidden_from=at)
                        _key_visibility(new, visible_from=at)
                    else:
                        bpy.data.objects.remove(old, do_unlink=True)
                        build_object(by_id[oid])
        elif r["op"] == "set_environment" and frames is None:
            set_environment(new_state["environment"])


def inventory() -> dict:
    inv = {}
    for oid, objs in city_objects().items():
        o = objs[0]
        entry = {"loc": [round(v, 4) for v in o.location], "location": o["city_location"],
                 "material": o.get("city_material", "")}
        if o.type == "FONT":
            entry["body"] = o.data.body
        inv[oid] = entry
    return {"objects": inv, "count": len(inv)}


def render_references(state: dict, out_dir: Path) -> list[Path]:
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x, sc.render.resolution_y = REF_SETTINGS["width"], REF_SETTINGS["height"]
    sc.render.resolution_percentage = 100
    sc.eevee.taa_render_samples = REF_SETTINGS["samples"]
    sc.view_settings.view_transform = "AgX"
    sc.render.image_settings.file_format = "PNG"
    out_dir.mkdir(parents=True, exist_ok=True)
    cam_data = bpy.data.cameras.new("REF_cam")
    cam = bpy.data.objects.new("REF_cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    paths = []
    for loc, c in state["ref_cameras"].items():
        cam.location = c["loc"]
        cam_data.lens = c["lens"]
        look_at(cam, c["target"])
        sc.render.filepath = str(out_dir / f"{loc}.png")
        bpy.ops.render.render(write_still=True)
        paths.append(out_dir / f"{loc}.png")
    bpy.data.objects.remove(cam, do_unlink=True)
    return paths
