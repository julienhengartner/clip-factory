"""Renders a Bobbington episode from a timeline JSON in ONE Blender pass.

    blender -b --factory-startup -P blender/render_episode.py -- <timeline.json> <out.mp4> [draft|final] [first last]

All sets live in one scene at different X offsets; characters are moved to their marks at each cut
(constant interpolation) and animated through their rigs. Camera instructions come from the episode.
"""
from __future__ import annotations

import math
import json
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "blender")]

from bobbington.bible import CAST, PALETTE  # noqa: E402
import animate  # noqa: E402
import characters  # noqa: E402
import scene_kit  # noqa: E402
from sets import SetBuilder  # noqa: E402

QUALITY = {"draft": (540, 960, 4), "final": (1080, 1920, 8)}
OFFSTAGE = Vector((-300.0, 0.0, 0.0))
PORTRAIT_HFOV = 2 * math.atan((36 * 9 / 16) / 2 / 35)   # 35 mm lens, sensor fitted to the height


def mark_of(builder: SetBuilder, set_name: str, mark: str):
    m = builder.marks[set_name].get(mark) or next(iter(builder.marks[set_name].values()))
    x, y, facing = m[0], m[1], m[2]
    z = m[3] if len(m) > 3 else 0.0
    return Vector((x, y, z)), math.radians(facing)


def key_transform(obj, frame: int, loc: Vector, rot_z: float) -> None:
    obj.location = loc
    obj.rotation_euler = (0, 0, rot_z)
    obj.keyframe_insert("location", frame=frame)
    obj.keyframe_insert("rotation_euler", frame=frame)


def head_point(char: dict, loc: Vector) -> Vector:
    d = char["dims"]
    return loc + Vector((0, 0, d["head_center_z"] - d["head_r"] * 0.35))


def key_camera(cam, frame: int, location: Vector, target: Vector) -> None:
    cam.location = location
    scene_kit.look_at(cam, target)
    cam.keyframe_insert("location", frame=frame)
    cam.keyframe_insert("rotation_euler", frame=frame)


def camera_for_shot(cam, shot: dict, positions: dict, chars: dict, builder: SetBuilder) -> None:
    f0, f1 = shot["start_frame"], max(shot["start_frame"], shot["end_frame"] - 1)
    c = shot["camera"]
    kind = c.get("type", "wide")
    if shot["set"] == "title_card":
        from sets import OFFSETS
        ox = OFFSETS["title_card"]
        key_camera(cam, f0, Vector((ox, -3.0, 2.1)), Vector((ox, 2.7, 2.15)))
        key_camera(cam, f1, Vector((ox, -2.5, 2.1)), Vector((ox, 2.7, 2.15)))
        return
    if kind in ("close", "push_in") and c.get("target") in positions:
        loc, face = positions[c["target"]]
        tgt = head_point(chars[c["target"]], loc)
        direction = Vector((math.sin(face) * 1 + 0.12, -math.cos(face), 0)).normalized()
        d0 = max(1.75, c.get("from") or (1.9 if kind == "close" else 2.5))
        d1 = max(1.55, c.get("to") or (1.75 if kind == "close" else 1.6))
        key_camera(cam, f0, tgt + direction * d0 + Vector((0, 0, 0.06)), tgt)
        key_camera(cam, f1, tgt + direction * d1 + Vector((0.04, 0, 0.04)), tgt)
        return
    targets = [t for t in (c.get("targets") or list(positions)) if t in positions]
    if not targets:
        targets = list(positions)
    pts = [head_point(chars[t], positions[t][0]) for t in targets]
    centre = sum(pts, Vector()) / len(pts)
    span = max((p - q).length for p in pts for q in pts) if len(pts) > 1 else 0.6
    if kind == "two_shot":
        d = max(2.3, (span + 0.6) / (2 * math.tan(PORTRAIT_HFOV / 2)))
        height = 0.1
    else:  # wide / static
        d = max(3.4, (span + 1.2) / (2 * math.tan(PORTRAIT_HFOV / 2)))
        height = 0.45
    look = centre - Vector((0, 0, 0.35 if kind != "two_shot" else 0.15))
    key_camera(cam, f0, centre + Vector((-0.15, -d, height)), look)
    key_camera(cam, f1, centre + Vector((0.15, -d * 0.94, height)), look)


def main(argv: list[str]) -> None:
    tl = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    out = Path(argv[1]).resolve()
    quality = argv[2] if len(argv) > 2 else "draft"
    stills = [int(x) for x in argv[3:]] if quality == "stills" else []
    frame_range = (int(argv[3]), int(argv[4])) if len(argv) > 4 and not stills else None
    w, h, samples = QUALITY["draft" if stills else quality]
    fps = tl["fps"]
    t0 = time.time()

    scene_kit.reset_scene()
    builder = SetBuilder(PALETTE)
    builder.mayors_office()
    builder.council_chamber()
    builder.main_street()
    pub_text = next((s["on_screen"].get("chalkboard", "") for s in tl["shots"] if s["set"] == "pub"), "")
    builder.pub(pub_text)
    title_shot = next((s for s in tl["shots"] if s["set"] == "title_card"), None)
    builder.title_card((title_shot or {}).get("on_screen", {}).get("title", "BOBBINGTON"),
                       (title_shot or {}).get("on_screen", {}).get("subtitle", tl["title"]))
    scene_kit.sun(energy=2.2)

    cast_ids = sorted({cid for s in tl["shots"] for cid in s["cast"]})
    chars = {cid: characters.build_character(cid, CAST[cid], PALETTE, location=OFFSTAGE) for cid in cast_ids}
    cam = scene_kit.camera((0, -4, 1.4), (0, 0, 1.2), lens=35)
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = 2.8

    # props that appear only from a given shot on (e.g. the commemorative plaque)
    reveal = {s["on_screen"]["prop"]: s["start_frame"] for s in tl["shots"] if s.get("on_screen", {}).get("prop")}
    for name, obj in builder.props.items():
        base = name.replace("_text", "")
        if base in reveal:
            obj.hide_render = True
            obj.keyframe_insert("hide_render", frame=0)
            obj.hide_render = False
            obj.keyframe_insert("hide_render", frame=reveal[base])

    for shot in tl["shots"]:
        f0, f1 = shot["start_frame"], max(shot["start_frame"] + 1, shot["end_frame"])
        positions = {}
        for cid, ch in chars.items():
            rig = ch["rig"]
            if cid in shot["cast"]:
                loc, face = mark_of(builder, shot["set"], shot["cast"][cid])
                positions[cid] = (loc, face)
                key_transform(rig, f0, loc, face)
                key_transform(rig, f1 - 1, loc, face)
                animate.rest(rig, f0)
                animate.brows(rig, f0, "neutral")
                animate.blinks([ch["parts"]["eye.L"], ch["parts"]["eye.R"], ch["parts"]["pupil.L"],
                                ch["parts"]["pupil.R"]], f0, f1, fps, f"{cid}{shot['id']}")
            else:
                key_transform(rig, f0, OFFSTAGE, 0.0)
        # where the conversation is: the camera picks up the dofs focus on the first target
        camera_for_shot(cam, shot, positions, chars, builder)
        focus = shot["camera"].get("target") or (shot["camera"].get("targets") or [None])[0]
        if focus in positions:
            cam.data.dof.focus_distance = max(0.5, (cam.location - head_point(chars[focus], positions[focus][0])).length)
            cam.data.keyframe_insert("dof.focus_distance", frame=f0)

        for line in shot["lines"]:
            spk = line["speaker"]
            ch = chars[spk]
            lf0, lf1 = line["start_frame"], line["end_frame"]
            animate.brows(ch["rig"], lf0, line["emotion"])
            animate.gesture(ch["rig"], line["action"], lf0, lf1, fps)
            animate.lip_sync(ch["parts"]["mouth"], lf0, line["mouth"])
            if line["action"] not in ("nod", "shake_head", "raise_arms", "scratch_head", "freeze"):
                animate.talking_head(ch["rig"], lf0, line["mouth"])
            # listeners look towards the speaker
            for cid, (loc, face) in positions.items():
                if cid == spk:
                    continue
                dx = positions[spk][0].x - loc.x
                animate.head(chars[cid]["rig"], lf0 + 3, turn=max(-0.6, min(0.6, -dx * 0.25)))
                animate.brows(chars[cid]["rig"], lf0 + 3, "deadpan" if cid == "margaret" else "neutral")

    for ch in chars.values():
        rig = ch["rig"]
        if rig.animation_data and rig.animation_data.action:
            animate.set_interpolation(rig, "BEZIER")
        # cuts: object transforms jump instantly
        for fc in _fcurves(rig):
            if fc.data_path in ("location", "rotation_euler"):
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT"
    for fc in _fcurves(cam):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"

    # title animation: pop-in of the title texts
    if title_shot:
        tf = title_shot["start_frame"]
        for name, delay in (("title_main", 0), ("title_sub", 6), ("title_tag", 12)):
            o = builder.props.get(name)
            if not o:
                continue
            o.scale = (0.01, 0.01, 0.01)
            o.keyframe_insert("scale", frame=tf + delay)
            o.scale = (1.12, 1.12, 1.12)
            o.keyframe_insert("scale", frame=tf + delay + 6)
            o.scale = (1, 1, 1)
            o.keyframe_insert("scale", frame=tf + delay + 10)

    sc = bpy.context.scene
    scene_kit.render_settings(w, h, fps=fps, samples=samples)
    if stills:  # one PNG per requested frame (visual checks)
        for f in stills:
            sc.frame_set(f)
            scene_kit.render_still(out.parent / f"{out.stem}_{f:05d}.png")
        print(f"STILLS={len(stills)} SECONDS={time.time() - t0:.1f}")
        return
    sc.frame_start, sc.frame_end = frame_range or (0, tl["total_frames"] - 1)
    sc.render.image_settings.file_format = "FFMPEG"
    sc.render.ffmpeg.format = "MPEG4"
    sc.render.ffmpeg.codec = "H264"
    sc.render.ffmpeg.constant_rate_factor = "HIGH"
    sc.render.ffmpeg.audio_codec = "NONE"
    sc.render.filepath = str(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"BUILD_SECONDS={time.time() - t0:.1f}")
    t1 = time.time()
    bpy.ops.render.render(animation=True)
    print(f"RENDER_SECONDS={time.time() - t1:.1f} FRAMES={sc.frame_end - sc.frame_start + 1}")


def _fcurves(obj):
    ad = obj.animation_data
    if not ad or not ad.action:
        return []
    fcs = getattr(ad.action, "fcurves", None)
    if fcs is not None and len(fcs):
        return list(fcs)
    return [fc for layer in ad.action.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
