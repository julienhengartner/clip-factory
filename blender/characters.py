"""Procedural, rigged cartoon characters for Bobbington (runs inside Blender 4.5, `bpy`).

Every character is built from the look spec in bobbington/bible.py, so proportions and colours stay identical
in every episode. Rig: one armature per character (root, spine, head, brows, arms, legs). All mesh parts are
bone-parented, so animation is done on the rig (blender/animate.py), not on camera moves over stills.

Conventions: Z up, characters face -Y (towards the default camera), origin at the feet.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Vector

# ------------------------------------------------------------------------------------------------
# materials
# ------------------------------------------------------------------------------------------------
_MAT_CACHE: dict[str, bpy.types.Material] = {}


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def colour(value: str, palette: dict) -> tuple[float, float, float, float]:
    h = palette.get(value, value).lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (1.0,)


def material(name: str, rgba, roughness: float = 0.6, pattern: str | None = None, sheen: float = 0.0,
             metallic: float = 0.0, emission: float = 0.0) -> bpy.types.Material:
    key = f"{name}|{rgba}|{pattern}|{roughness}|{metallic}"
    if key in _MAT_CACHE:
        return _MAT_CACHE[key]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission:
        bsdf.inputs["Emission Color"].default_value = rgba
        bsdf.inputs["Emission Strength"].default_value = emission
    if pattern in ("tweed", "knit_vest", "floral"):
        tex = nt.nodes.new("ShaderNodeTexNoise" if pattern != "pinstripe" else "ShaderNodeTexWave")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        dark = tuple(x * 0.55 for x in rgba[:3]) + (1.0,)
        light = tuple(min(1.0, x * 1.35) for x in rgba[:3]) + (1.0,)
        if pattern == "tweed":
            tex.inputs["Scale"].default_value = 180.0
            tex.inputs["Detail"].default_value = 8.0
        elif pattern == "knit_vest":
            tex.inputs["Scale"].default_value = 60.0
        elif pattern == "floral":
            tex.inputs["Scale"].default_value = 25.0
            light = (0.95, 0.85, 0.6, 1.0)
        else:  # pinstripe
            tex.inputs["Scale"].default_value = 45.0
            tex.wave_type = "BANDS"
            ramp.color_ramp.elements[0].position = 0.9
            light = (0.8, 0.8, 0.85, 1.0)
        ramp.color_ramp.elements[0].color = dark if pattern != "pinstripe" else rgba
        ramp.color_ramp.elements[1].color = light
        ramp.color_ramp.elements[0].position = 0.35 if pattern != "pinstripe" else 0.92
        ramp.color_ramp.elements[1].position = 0.75 if pattern != "pinstripe" else 0.97
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["Factor"].default_value = 0.35 if pattern != "pinstripe" else 1.0
        mix.inputs["A"].default_value = rgba
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], mix.inputs["B"])
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = rgba
    if sheen:
        bsdf.inputs["Sheen Weight"].default_value = sheen
    _MAT_CACHE[key] = mat
    return mat


# ------------------------------------------------------------------------------------------------
# primitives
# ------------------------------------------------------------------------------------------------
def _finish(obj, mat, smooth=True, subsurf=0):
    obj.data.materials.append(mat)
    if smooth:
        for p in obj.data.polygons:
            p.use_smooth = True
    if subsurf:
        m = obj.modifiers.new("Subsurf", "SUBSURF")
        m.levels = subsurf
        m.render_levels = subsurf
    return obj


def sphere(name, loc, scale, mat, segments=32, rings=16, collection=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1.0, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    return _finish(o, mat)


def cylinder(name, loc, radius, depth, mat, rot=(0, 0, 0), vertices=24, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    return _finish(o, mat)


def cone(name, loc, r1, r2, depth, mat, rot=(0, 0, 0), vertices=24):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r1, radius2=r2, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return _finish(o, mat)


def torus(name, loc, major, minor, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=loc, rotation=rot,
                                     major_segments=32, minor_segments=12)
    o = bpy.context.active_object
    o.name = name
    return _finish(o, mat)


def cube(name, loc, scale, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    _finish(o, mat, smooth=False)
    if bevel:
        m = o.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = 3
    return o


def curve_tube(name, points, radius, mat, taper_end=True):
    """Bevelled bezier tube through points – used for moustaches, eyebrows, handles."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 4
    cu.resolution_u = 12
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(points) - 1)
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    if taper_end:
        n = len(sp.bezier_points)
        for i, bp in enumerate(sp.bezier_points):
            bp.radius = 0.35 + 0.65 * math.sin(math.pi * (i + 0.5) / n)
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    return o


# ------------------------------------------------------------------------------------------------
# rig
# ------------------------------------------------------------------------------------------------
BONES = ["root", "spine", "head", "brow.L", "brow.R", "arm.L", "arm.R", "leg.L", "leg.R"]


def build_armature(cid: str, dims: dict) -> bpy.types.Object:
    arm_data = bpy.data.armatures.new(f"RIG_{cid}")
    arm = bpy.data.objects.new(f"RIG_{cid}", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones

    def bone(name, head, tail, parent=None):
        b = eb.new(name)
        b.head, b.tail = Vector(head), Vector(tail)
        if parent:
            b.parent = eb[parent]
        return b

    hip_z, neck_z, head_c = dims["hip_z"], dims["neck_z"], dims["head_center_z"]
    sh_x, sh_z = dims["shoulder_x"], dims["shoulder_z"]
    bone("root", (0, 0, 0), (0, 0.25, 0))
    bone("spine", (0, 0, hip_z), (0, 0, neck_z), "root")
    bone("head", (0, 0, neck_z), (0, 0, head_c + dims["head_r"]), "spine")
    for side, s in (("L", 1), ("R", -1)):
        brow_z = head_c + dims["head_r"] * 0.38
        bone(f"brow.{side}", (s * dims["head_r"] * 0.35, -dims["head_r"] * 0.9, brow_z),
             (s * dims["head_r"] * 0.35, -dims["head_r"] * 1.05, brow_z), "head")
        bone(f"arm.{side}", (s * sh_x, 0, sh_z), (s * sh_x, 0, sh_z - dims["arm_len"]), "spine")
        bone(f"leg.{side}", (s * dims["hip_x"], 0, hip_z), (s * dims["hip_x"], 0, 0.05), "root")
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
    arm.show_in_front = False
    arm.hide_render = True
    return arm


def attach(obj, arm, bone_name):
    """Rigid bone parenting while keeping the current world transform."""
    bpy.context.view_layer.update()
    mw = obj.matrix_world.copy()
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    bpy.context.view_layer.update()
    obj.matrix_world = mw


# ------------------------------------------------------------------------------------------------
# character builder
# ------------------------------------------------------------------------------------------------
BUILDS = {  # torso half-width (x), half-depth (y) multipliers relative to height
    "round": (0.20, 0.17), "tall_thin": (0.115, 0.09), "slim": (0.125, 0.095), "broad": (0.18, 0.13),
    "lanky": (0.11, 0.085),
}


def build_character(cid: str, spec: dict, palette: dict, location=(0, 0, 0)) -> dict:
    """Builds a rigged character. Returns {'rig', 'parts', 'dims'}."""
    look = spec["look"]
    H = look["height"]
    head_r = look["head"] * 0.78
    bx, by = BUILDS.get(look["build"], (0.14, 0.1))
    leg_len = H * 0.30
    hip_z = leg_len
    head_center_z = H - head_r
    neck_z = head_center_z - head_r * 0.92
    torso_h = neck_z - hip_z
    dims = dict(height=H, head_r=head_r, hip_z=hip_z, neck_z=neck_z, head_center_z=head_center_z,
                shoulder_x=H * bx * 0.92, shoulder_z=neck_z - torso_h * 0.16, arm_len=torso_h * 0.9,
                hip_x=H * bx * 0.45, torso_w=H * bx, torso_d=H * by)
    out = look["outfit"]
    col = lambda v: colour(v, palette)  # noqa: E731
    skin = material(f"{cid}_skin", col(look["skin"]), 0.55, sheen=0.2)
    jacket = material(f"{cid}_jacket", col(out["jacket"]), 0.8, out.get("jacket_pattern"))
    lower = material(f"{cid}_lower", col(out.get("trousers") or out.get("skirt")), 0.8)
    shirt = material(f"{cid}_shirt", col(out.get("shirt", "cream")), 0.7)
    shoes = material(f"{cid}_shoes", col(out["shoes"]), 0.35)
    white = material("eye_white", (0.95, 0.95, 0.93, 1), 0.2)
    pupil = material("pupil", (0.02, 0.02, 0.025, 1), 0.1)
    mouth_m = material("mouth", (0.06, 0.008, 0.012, 1), 0.6)

    rig = build_armature(cid, dims)
    parts: dict[str, bpy.types.Object] = {}

    def add(name, obj, bone):
        obj.name = f"{cid}_{name}"
        attach(obj, rig, bone)
        parts[name] = obj
        return obj

    # body
    tz = hip_z + torso_h * 0.5
    add("torso", sphere("t", (0, 0, tz), (dims["torso_w"], dims["torso_d"], torso_h * 0.62), jacket), "spine")
    add("shirt_front", sphere("sf", (0, -dims["torso_d"] * 0.55, tz + torso_h * 0.18),
                              (dims["torso_w"] * 0.35, dims["torso_d"] * 0.5, torso_h * 0.33), shirt), "spine")
    if out.get("skirt"):
        add("skirt", cone("sk", (0, 0, hip_z - leg_len * 0.15), dims["torso_w"] * 1.05, dims["torso_w"] * 0.8,
                          leg_len * 0.55, lower), "spine")
    for side, s in (("L", 1), ("R", -1)):
        lx = s * dims["hip_x"]
        add(f"leg.{side}", cylinder("lg", (lx, 0, hip_z * 0.5), H * 0.045, hip_z, lower), f"leg.{side}")
        add(f"shoe.{side}", sphere("sh", (lx, -H * 0.03, H * 0.025), (H * 0.05, H * 0.085, H * 0.032), shoes),
            f"leg.{side}")
        ax, az = s * dims["shoulder_x"], dims["shoulder_z"]
        add(f"shoulder.{side}", sphere("so", (ax, 0, az), (H * 0.058,) * 3, jacket), f"arm.{side}")
        add(f"arm.{side}", cylinder("ar", (ax, 0, az - dims["arm_len"] / 2), H * 0.042, dims["arm_len"], jacket),
            f"arm.{side}")
        add(f"cuff.{side}", cylinder("cf", (ax, 0, az - dims["arm_len"] + 0.01), H * 0.047, 0.04, shirt), f"arm.{side}")
        add(f"hand.{side}", sphere("hd", (ax, -0.01, az - dims["arm_len"] - H * 0.02), (H * 0.04,) * 3, skin),
            f"arm.{side}")

    # head & face
    hc = Vector((0, 0, head_center_z))
    add("head", sphere("h", hc, (head_r, head_r * 0.95, head_r * 1.02), skin), "head")
    add("neck", cylinder("nk", (0, 0, neck_z + head_r * 0.05), head_r * 0.42, head_r * 0.5, skin), "head")
    nose_scale = {"bulb": (0.26, 0.24, 0.24), "pointed": (0.12, 0.2, 0.13), "long": (0.13, 0.26, 0.14),
                  "button": (0.14, 0.13, 0.12)}.get(look.get("nose", "bulb"), (0.18, 0.18, 0.18))
    add("nose", sphere("n", hc + Vector((0, -head_r * 0.98, -head_r * 0.08)),
                       tuple(head_r * v for v in nose_scale), skin), "head")
    ey = -head_r * 0.82
    for side, s in (("L", 1), ("R", -1)):
        ex = s * head_r * 0.36
        add(f"eye.{side}", sphere("e", hc + Vector((ex, ey, head_r * 0.15)), (head_r * 0.25, head_r * 0.14, head_r * 0.29),
                                  white), "head")
        add(f"pupil.{side}", sphere("p", hc + Vector((ex, ey - head_r * 0.13, head_r * 0.12)),
                                    (head_r * 0.11, head_r * 0.06, head_r * 0.125), pupil), "head")
        add(f"ear.{side}", sphere("ea", hc + Vector((s * head_r * 0.98, 0, 0)), (head_r * 0.12, head_r * 0.2, head_r * 0.26),
                                  skin), "head")
    # mouth: dark ellipsoid, scaled in Z for lip sync
    mouth_z = -head_r * (0.6 if look.get("moustache") else 0.48)
    add("mouth", sphere("m", hc + Vector((0, -head_r * 0.8, mouth_z)),
                        (head_r * 0.28, head_r * 0.12, head_r * 0.045), mouth_m), "head")

    # eyebrows (bone-driven)
    brows = look.get("eyebrows")
    if brows:
        bm = material(f"{cid}_brow", col(brows["colour"]), 0.9)
        thick = {"bushy": 0.075, "heavy": 0.065, "thin": 0.025, "arched": 0.035, "worried": 0.035}[brows["style"]]
        for side, s in (("L", 1), ("R", -1)):
            bz = head_center_z + head_r * 0.42
            tilt = {"worried": 0.12, "arched": -0.05}.get(brows["style"], 0.0)
            pts = [(s * head_r * 0.15, -head_r * 0.93, bz - s * 0 + tilt * head_r * s * 0),
                   (s * head_r * 0.36, -head_r * 0.97, bz + head_r * (0.08 if brows["style"] == "arched" else 0.03)),
                   (s * head_r * 0.58, -head_r * 0.85, bz + tilt * head_r)]
            add(f"brow.{side}", curve_tube("br", pts, head_r * thick, bm), f"brow.{side}")

    # moustache
    mo = look.get("moustache")
    if mo:
        mm = material(f"{cid}_moustache", col(mo["colour"]), 0.9)
        mz = head_center_z - head_r * 0.28
        my = -head_r * 1.0
        for s in (1, -1):
            if mo["style"] == "bushy_handlebar":
                pts = [(s * head_r * 0.03, my - head_r * 0.12, mz), (s * head_r * 0.4, my - head_r * 0.05, mz - head_r * 0.04),
                       (s * head_r * 0.8, my + head_r * 0.15, mz + head_r * 0.05),
                       (s * head_r * 0.98, my + head_r * 0.25, mz + head_r * 0.24)]
                add(f"moustache.{s}", curve_tube("mo", pts, head_r * 0.13, mm), "head")
            else:  # pencil
                pts = [(s * head_r * 0.02, my - head_r * 0.1, mz), (s * head_r * 0.32, my - head_r * 0.04, mz - head_r * 0.02)]
                add(f"moustache.{s}", curve_tube("mo", pts, head_r * 0.03, mm, taper_end=False), "head")
    beard = look.get("beard")
    if beard:
        add("stubble", sphere("st", hc + Vector((0, -head_r * 0.2, -head_r * 0.78)),
                              (head_r * 0.72, head_r * 0.78, head_r * 0.3),
                              material(f"{cid}_stubble", col(beard["colour"]), 0.95)), "head")
        parts["stubble"].scale = parts["stubble"].scale  # stubble sits slightly inside the face

    # glasses
    gl = look.get("glasses")
    if gl:
        gm = material(f"{cid}_glasses", col(gl["frame"]), 0.25, metallic=0.9 if gl["frame"] == "gold" else 0.0)
        for side, s in (("L", 1), ("R", -1)):
            r = head_r * (0.24 if gl["style"] == "round" else 0.2)
            add(f"lens.{side}", torus("gl", hc + Vector((s * head_r * 0.36, -head_r * 1.02, head_r * 0.13)),
                                      r, head_r * 0.025, gm, rot=(math.pi / 2, 0, 0)), "head")
        add("bridge", cylinder("bg", hc + Vector((0, -head_r * 1.04, head_r * 0.16)), head_r * 0.02, head_r * 0.25, gm,
                               rot=(0, math.pi / 2, 0)), "head")

    # hair / hats
    hair = look.get("hair", {})
    hm = material(f"{cid}_hair", col(hair.get("colour", "#333333")), 0.85)
    st = hair.get("style")
    top = hc + Vector((0, 0, head_r * 0.85))
    if st == "bald_ring":
        add("hair", torus("hr", hc + Vector((0, head_r * 0.15, head_r * 0.12)), head_r * 0.92, head_r * 0.14, hm,
                          rot=(math.radians(-12), 0, 0)), "head")
    elif st == "tight_bun":
        add("hair", sphere("hr", hc + Vector((0, head_r * 0.22, head_r * 0.38)), (head_r * 1.02, head_r * 0.92, head_r * 0.78),
                           hm), "head")
        add("bun", sphere("bn", hc + Vector((0, head_r * 0.55, head_r * 0.85)), (head_r * 0.38,) * 3, hm), "head")
    elif st == "slick_side_part":
        add("hair", sphere("hr", hc + Vector((head_r * 0.04, head_r * 0.2, head_r * 0.42)),
                           (head_r * 1.03, head_r * 0.95, head_r * 0.72), hm), "head")
        add("quiff", sphere("qf", hc + Vector((-head_r * 0.25, -head_r * 0.55, head_r * 0.78)),
                            (head_r * 0.55, head_r * 0.35, head_r * 0.22), hm), "head")
    elif st == "big_curls":
        import random
        rnd = random.Random(cid)
        for i in range(16):
            a = rnd.uniform(0, 2 * math.pi)
            e = rnd.uniform(0.05, 1.2)
            p = hc + Vector((math.cos(a) * math.cos(e) * head_r, abs(math.sin(a)) * head_r * 0.5 + head_r * 0.15,
                             math.sin(e) * head_r * 0.95 + head_r * 0.15))
            add(f"curl{i}", sphere("cl", p, (head_r * 0.42,) * 3, hm, segments=16, rings=8), "head")
    elif st == "flat_cap":
        add("hair", cylinder("cap", top + Vector((0, 0, -head_r * 0.1)), head_r * 1.02, head_r * 0.3, hm,
                             scale=(1, 1.08, 1)), "head")
        add("brim", cylinder("brm", top + Vector((0, -head_r * 0.75, -head_r * 0.2)), head_r * 0.55, head_r * 0.06, hm,
                             scale=(1.3, 0.8, 1)), "head")
    elif st == "custodian_helmet":
        add("hair", cone("hel", top + Vector((0, 0, head_r * 0.35)), head_r * 1.05, head_r * 0.55, head_r * 1.5, hm),
            "head")
        add("helmet_top", sphere("hlt", top + Vector((0, 0, head_r * 1.1)), (head_r * 0.55, head_r * 0.55, head_r * 0.35), hm),
            "head")
        add("badge", sphere("bd", top + Vector((0, -head_r * 0.85, head_r * 0.3)), (head_r * 0.16, head_r * 0.05, head_r * 0.2),
                            material("silver", (0.8, 0.8, 0.85, 1), 0.2, metallic=1.0)), "head")

    # neckwear
    neck = out.get("neck", {"type": "none"})
    nm = material(f"{cid}_neck", col(neck.get("colour", "ink")), 0.5)
    nz, ny = neck_z - head_r * 0.22, -dims["torso_d"] * 0.95
    if neck["type"] == "bow_tie":
        for s in (1, -1):
            add(f"bow.{s}", cone("bw", (s * head_r * 0.15, ny, nz), head_r * 0.14, head_r * 0.02, head_r * 0.26, nm,
                                 rot=(0, s * math.pi / 2, 0), vertices=4), "spine")
        add("bow_knot", sphere("bk", (0, ny - 0.005, nz), (head_r * 0.08,) * 3, nm), "spine")
    elif neck["type"] == "tie":
        add("tie", cone("tie", (0, ny, nz - torso_h * 0.2), head_r * 0.13, head_r * 0.05, torso_h * 0.4, nm,
                        rot=(math.pi, 0, 0), vertices=4), "spine")
    elif neck["type"] == "pearls":
        add("pearls", torus("pr", (0, -dims["torso_d"] * 0.2, nz - head_r * 0.05), dims["torso_w"] * 0.55, head_r * 0.05,
                            material("pearl", (0.95, 0.93, 0.88, 1), 0.2), rot=(math.radians(70), 0, 0)), "spine")
    elif neck["type"] == "brooch":
        add("brooch", sphere("bro", (head_r * 0.3, ny, nz - torso_h * 0.15), (head_r * 0.1,) * 3,
                             material("gold_metal", col("gold"), 0.25, metallic=1.0)), "spine")

    # accessories
    acc = out.get("accessory")
    gold = material("gold_metal", col("gold"), 0.25, metallic=1.0)
    if acc == "mayoral_chain":
        add("chain", torus("ch", (0, -dims["torso_d"] * 0.25, neck_z - torso_h * 0.15), dims["torso_w"] * 0.75,
                           head_r * 0.04, gold, rot=(math.radians(65), 0, 0)), "spine")
        add("medal", cylinder("md", (0, -dims["torso_d"] * 1.0, neck_z - torso_h * 0.45), head_r * 0.2, 0.02, gold,
                              rot=(math.pi / 2, 0, 0)), "spine")
    elif acc == "clipboard":
        add("clipboard", cube("cb", (dims["shoulder_x"] * 0.4, -dims["torso_d"] * 1.3, neck_z - torso_h * 0.35),
                              (0.22, 0.015, 0.3), material("board", col("#8A6A45"), 0.6)), "arm.R")
    elif acc == "biscuit_tin":
        add("tin", cylinder("tn", (0, -dims["torso_d"] * 1.25, hip_z + torso_h * 0.15), 0.12, 0.08,
                            material("tin", col("racing_green"), 0.3, metallic=0.6), rot=(math.pi / 2, 0, 0)), "arm.L")
    elif acc == "tea_towel":
        add("towel", cube("tw", (-dims["shoulder_x"] * 0.9, -dims["torso_d"] * 0.3, neck_z - torso_h * 0.2),
                          (0.08, 0.04, 0.28), material("towel", col("cream"), 0.9)), "spine")
    elif acc == "notebook":
        add("notebook", cube("nb", (-dims["shoulder_x"], -0.08, dims["shoulder_z"] - dims["arm_len"] - 0.05),
                             (0.09, 0.02, 0.13), material("notebook", col("ink"), 0.7)), "arm.R")
    elif acc == "rosette":
        add("rosette", cylinder("rs", (dims["torso_w"] * 0.5, -dims["torso_d"] * 1.0, neck_z - torso_h * 0.2),
                                head_r * 0.15, 0.02, material("rosette", col("burgundy"), 0.6), rot=(math.pi / 2, 0, 0)),
            "spine")

    rig.location = location
    return {"rig": rig, "parts": parts, "dims": dims}
