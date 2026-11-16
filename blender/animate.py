"""Character animation library (rig-based – real character animation, not camera moves over stills).

Bone conventions (verified with test renders):
  arms   : forward = -rotation X (both sides); outward = -Z (left) / +Z (right)
  head   : nod = +X (chin down), turn = Y, tilt = Z
  spine  : lean forward = +X
Facial animation: mouth opening from the voice loudness per frame (lip sync), blinks, brow poses per emotion.
"""
from __future__ import annotations

import math
import random

import bpy

BROW_BY_EMOTION = {  # (left_raise, right_raise) in radians on the brow bones
    "neutral": (0.0, 0.0), "proud": (0.25, 0.25), "grand": (0.35, 0.35), "deadpan": (-0.05, 0.2),
    "smug": (0.3, -0.05), "smarmy": (0.25, 0.1), "thrilled": (0.35, 0.35), "confused": (0.3, -0.15),
    "certain": (-0.1, -0.1), "grumpy": (-0.3, -0.3), "panicked": (0.45, 0.45), "shocked": (0.5, 0.5),
}


def key_bone(rig, bone: str, frame: int, rot: tuple[float, float, float]) -> None:
    pb = rig.pose.bones[bone]
    pb.rotation_euler = rot
    pb.keyframe_insert("rotation_euler", frame=frame)


def arm(rig, side: str, frame: int, forward: float = 0.0, out: float = 0.0) -> None:
    key_bone(rig, f"arm.{side}", frame, (-forward, 0.0, out if side == "R" else -out))


def head(rig, frame: int, nod: float = 0.0, turn: float = 0.0, tilt: float = 0.0) -> None:
    key_bone(rig, "head", frame, (nod, turn, tilt))


def spine(rig, frame: int, lean: float = 0.0, twist: float = 0.0, side: float = 0.0) -> None:
    key_bone(rig, "spine", frame, (lean, twist, side))


def brows(rig, frame: int, emotion: str) -> None:
    l, r = BROW_BY_EMOTION.get(emotion, (0.0, 0.0))
    key_bone(rig, "brow.L", frame, (l, 0.0, 0.0))
    key_bone(rig, "brow.R", frame, (r, 0.0, 0.0))


def rest(rig, frame: int) -> None:
    for side in ("L", "R"):
        arm(rig, side, frame, 0.05, 0.08)
    head(rig, frame)
    spine(rig, frame)


# --- gestures (keyframed between f0 and f1) ---------------------------------------------------
def gesture(rig, action: str, f0: int, f1: int, fps: int) -> None:
    mid = (f0 + f1) // 2
    q = max(2, fps // 6)  # quick move ~ 1/6 s
    rest(rig, max(0, f0 - 1))
    if action == "slam_desk":
        arm(rig, "R", f0 + q, 1.6, 0.2)
        arm(rig, "L", f0 + q, 1.4, 0.2)
        arm(rig, "R", f0 + 2 * q, 0.9, 0.1)
        arm(rig, "L", f0 + 2 * q, 0.8, 0.1)
        spine(rig, f0 + 2 * q, 0.15)
        spine(rig, f0 + 4 * q, 0.0)
    elif action == "raise_arms":
        for side in ("L", "R"):
            arm(rig, side, f0 + 2 * q, 0.4, 2.3)
            arm(rig, side, f1 - q, 0.4, 2.2)
        head(rig, f0 + 2 * q, nod=-0.2)
    elif action == "nod":
        for k in range(3):
            head(rig, f0 + k * 2 * q, nod=0.0)
            head(rig, f0 + k * 2 * q + q, nod=0.3)
    elif action == "shake_head":
        for k in range(4):
            head(rig, f0 + k * q, turn=(0.35 if k % 2 else -0.35))
        head(rig, f0 + 4 * q, turn=0.0)
    elif action == "fold_arms":
        for side in ("L", "R"):
            arm(rig, side, f0 + 2 * q, 1.3, -0.9)
            arm(rig, side, f1, 1.3, -0.9)
        head(rig, f0 + 2 * q, tilt=0.12)
    elif action == "point":
        arm(rig, "R", f0 + 2 * q, 1.5, 0.15)
        arm(rig, "R", f1 - q, 1.45, 0.15)
    elif action == "point_self":
        arm(rig, "R", f0 + 2 * q, 1.3, -0.95)
        arm(rig, "R", f1 - q, 1.3, -0.95)
        head(rig, f0 + 2 * q, nod=-0.15, tilt=0.1)
    elif action == "thumbs_up":
        arm(rig, "R", f0 + 2 * q, 1.9, 0.3)
        arm(rig, "R", f1 - q, 1.9, 0.3)
        head(rig, f0 + 2 * q, tilt=-0.15)
    elif action == "stamp":
        n = max(1, min(3, (f1 - f0) // (3 * q)))
        for k in range(n):
            arm(rig, "R", f0 + k * 3 * q + q, 1.7, 0.2)
            arm(rig, "R", f0 + k * 3 * q + 2 * q, 0.9, 0.1)
    elif action == "gossip_lean":
        spine(rig, f0 + 2 * q, 0.2, side=0.1)
        arm(rig, "R", f0 + 2 * q, 2.3, -0.6)
        arm(rig, "R", f1 - q, 2.3, -0.6)
        spine(rig, f1 - q, 0.18, side=0.1)
    elif action == "scratch_head":
        arm(rig, "R", f0 + 2 * q, 2.6, 0.9)
        for k in range(3):
            arm(rig, "R", f0 + 3 * q + k * q, 2.6 + (0.15 if k % 2 else 0), 0.9)
        head(rig, f0 + 2 * q, tilt=-0.2)
    elif action == "polish_glass":
        for k in range(max(2, (f1 - f0) // (2 * q))):
            arm(rig, "R", f0 + k * 2 * q, 1.2 + 0.15 * math.sin(k), -0.4 + 0.15 * math.cos(k))
            arm(rig, "L", f0 + k * 2 * q, 1.1, -0.5)
    elif action == "wring_hands":
        for k in range(max(2, (f1 - f0) // q)):
            arm(rig, "L", f0 + k * q, 1.2 + (0.15 if k % 2 else 0), -0.6)
            arm(rig, "R", f0 + k * q, 1.2 + (0 if k % 2 else 0.15), -0.6)
        spine(rig, f0 + 2 * q, 0.12)
    elif action == "lift_clipboard":
        arm(rig, "R", f0 + 2 * q, 0.75, -0.2)
        arm(rig, "R", f1 - q, 0.75, -0.2)
        head(rig, f0 + 2 * q, nod=0.1)
    elif action == "shrug":
        for side in ("L", "R"):
            arm(rig, side, f0 + 2 * q, 0.6, 0.6)
        head(rig, f0 + 2 * q, tilt=0.15)
    elif action == "freeze":
        rest(rig, f0)
        rest(rig, f1)
    # settle back to rest shortly after the line ends
    rest(rig, f1 + 2 * q)


def lip_sync(mouth_obj, start_frame: int, envelope: list[float], open_scale: float = 2.6) -> None:
    base = tuple(mouth_obj.scale)
    mouth_obj.scale = base
    mouth_obj.keyframe_insert("scale", frame=max(0, start_frame - 1))
    for i, v in enumerate(envelope):
        mouth_obj.scale = (base[0] * (1.0 - 0.15 * v), base[1], base[2] * (1.0 + open_scale * v))
        mouth_obj.keyframe_insert("scale", frame=start_frame + i)
    mouth_obj.scale = base
    mouth_obj.keyframe_insert("scale", frame=start_frame + len(envelope) + 1)


def talking_head(rig, start_frame: int, envelope: list[float]) -> None:
    """Small head motion that follows the speech rhythm."""
    for i in range(0, len(envelope), 6):
        v = envelope[i]
        head(rig, start_frame + i, nod=0.06 * v - 0.02, turn=0.04 * math.sin(i / 9), tilt=0.03 * math.sin(i / 13))


def blinks(eyes: list, f_start: int, f_end: int, fps: int, seed: str) -> None:
    rnd = random.Random(seed)
    f = f_start + rnd.randint(fps // 2, 2 * fps)
    bases = [tuple(e.scale) for e in eyes]
    while f < f_end - 4:
        for e, b in zip(eyes, bases):
            e.scale = b
            e.keyframe_insert("scale", frame=f)
            e.scale = (b[0], b[1], b[2] * 0.1)
            e.keyframe_insert("scale", frame=f + 2)
            e.scale = b
            e.keyframe_insert("scale", frame=f + 4)
        f += rnd.randint(int(2.2 * fps), int(4.5 * fps))


def breathing(rig, f_start: int, f_end: int, fps: int) -> None:
    period = int(fps * 3.2)
    for f in range(f_start, f_end, period // 2):
        phase = ((f - f_start) // (period // 2)) % 2
        spine(rig, f, lean=0.015 if phase else -0.01)


def set_interpolation(obj, kind: str = "BEZIER") -> None:
    ad = obj.animation_data
    if not ad or not ad.action:
        return
    fcurves = getattr(ad.action, "fcurves", None)
    if fcurves is None:  # Blender 4.4+ layered actions
        fcurves = [fc for layer in ad.action.layers for strip in layer.strips
                   for bag in strip.channelbags for fc in bag.fcurves]
    for fc in fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = kind
