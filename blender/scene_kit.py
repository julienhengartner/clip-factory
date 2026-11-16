"""Shared scene utilities: reset, render settings, lights, camera, text, backdrops (Blender 4.5)."""
from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector

from characters import colour, material


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if not bpy.context.scene.world:
        bpy.context.scene.world = bpy.data.worlds.new("World")


def render_settings(width: int, height: int, fps: int = 24, samples: int = 16, engine: str = "BLENDER_EEVEE_NEXT") -> None:
    sc = bpy.context.scene
    sc.render.engine = engine
    sc.render.resolution_x, sc.render.resolution_y = width, height
    sc.render.resolution_percentage = 100
    sc.render.fps = fps
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    if hasattr(sc, "eevee"):
        sc.eevee.taa_render_samples = samples
        if hasattr(sc.eevee, "use_shadows"):
            sc.eevee.use_shadows = True
        if hasattr(sc.eevee, "use_raytracing"):
            sc.eevee.use_raytracing = False
    world = sc.world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.55, 0.62, 0.7, 1)
        bg.inputs["Strength"].default_value = 0.6


def look_at(obj, target) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def camera(location, target, lens=35.0, name="Camera") -> bpy.types.Object:
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = lens
    cam_data.clip_end = 300
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = location
    look_at(cam, target)
    bpy.context.scene.camera = cam
    return cam


def area_light(name, location, target, energy, size, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.size, ld.color = energy, size, color
    o = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(o)
    o.location = location
    look_at(o, target)
    return o


def sun(name="Sun", rotation=(math.radians(50), 0, math.radians(30)), energy=3.0, color=(1.0, 0.95, 0.85)):
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy, ld.color = energy, color
    ld.angle = math.radians(5)
    o = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(o)
    o.rotation_euler = rotation
    return o


def three_point_lights(target=(0, 0, 1)) -> None:
    t = Vector(target)
    area_light("Key", t + Vector((-2.5, -3.5, 2.5)), t, 900, 3.0, (1.0, 0.93, 0.82))
    area_light("Fill", t + Vector((3.0, -3.0, 1.2)), t, 350, 4.0, (0.85, 0.9, 1.0))
    area_light("Rim", t + Vector((0.5, 3.5, 2.8)), t, 600, 2.0, (1.0, 0.85, 0.6))


def studio_backdrop(colour_name="cream") -> None:
    from bobbington.bible import PALETTE
    m = material("backdrop", colour(colour_name, PALETTE), 0.9)
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.data.materials.append(m)
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 6, 10), rotation=(math.radians(90), 0, 0))
    bpy.context.active_object.data.materials.append(m)


def label(text, location, size=0.1, colour_name="ink", rotation=(math.radians(90), 0, 0), extrude=0.003,
          align="CENTER", font_path: str | None = "C:/Windows/Fonts/georgiab.ttf"):
    from bobbington.bible import PALETTE
    cu = bpy.data.curves.new(f"txt_{text[:12]}", "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    cu.align_y = "CENTER"
    if font_path and Path(font_path).is_file():
        cu.font = bpy.data.fonts.load(font_path, check_existing=True)
    o = bpy.data.objects.new(f"txt_{text[:12]}", cu)
    bpy.context.collection.objects.link(o)
    o.location, o.rotation_euler = location, rotation
    o.data.materials.append(material(f"txt_{colour_name}", colour(colour_name, PALETTE), 0.5))
    return o


def render_still(path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sc = bpy.context.scene
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
