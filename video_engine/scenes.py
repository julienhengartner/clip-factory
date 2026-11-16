"""Einzelne Einstellungen (Shots) aus Standbildern mit Kamerabewegung rendern – keine statischen Standbilder."""
from __future__ import annotations

from pathlib import Path

from config import Settings
from storage.models import Scene, Shot
from video_engine.ffmpeg import run_ffmpeg

MOTIONS = ["zoom_in", "pan_up", "zoom_out", "pan_left", "pan_down", "pan_right"]


def plan_shots(scenes: list[Scene], fps: int, max_shot_s: float) -> list[Scene]:
    """Teilt jede Szene in Shots von höchstens max_shot_s; Grenzen liegen exakt auf Frames (kein Drift)."""
    out, t, m = [], 0.0, 0
    for sc in scenes:
        n = max(1, int(-(-sc.duration_s // max_shot_s)))  # aufrunden
        shots = []
        for k in range(n):
            start_abs = t + sc.duration_s * k / n
            end_abs = t + sc.duration_s * (k + 1) / n
            f0, f1 = round(start_abs * fps), round(end_abs * fps)
            shots.append(Shot(start=round(start_abs - t, 4), duration=(f1 - f0) / fps,
                              motion=MOTIONS[m % len(MOTIONS)], variant=k))
            m += 1
        out.append(sc.model_copy(update={"shots": shots, "start_s": round(t, 4)}))
        t += sc.duration_s
    return out


def motion_filter(motion: str, w: int, h: int, frames: int, fps: int) -> tuple[list[str], str]:
    """Gibt (Eingabeoptionen, Filter) für eine Bewegung zurück. Eingabebild ist 1,2x überdimensioniert."""
    dur = frames / fps
    if motion in ("zoom_in", "zoom_out"):
        z = f"1+0.12*on/{max(frames - 1, 1)}" if motion == "zoom_in" else f"1.12-0.12*on/{max(frames - 1, 1)}"
        vf = (f"scale={w * 2}:{h * 2},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={w}x{h}:fps={fps}")
        return [], vf
    axis = {"pan_up": ("(iw-ow)/2", f"(ih-oh)*(1-t/{dur:.4f})"), "pan_down": ("(iw-ow)/2", f"(ih-oh)*t/{dur:.4f}"),
            "pan_left": (f"(iw-ow)*(1-t/{dur:.4f})", "(ih-oh)/2"), "pan_right": (f"(iw-ow)*t/{dur:.4f}", "(ih-oh)/2")}
    x, y = axis.get(motion, ("(iw-ow)/2", "(ih-oh)/2"))
    return ["-loop", "1", "-framerate", str(fps)], f"crop={w}:{h}:x='{x}':y='{y}'"


def render_shot(image: Path, shot: Shot, out_path: Path, settings: Settings) -> Path:
    w, h, fps = settings.video_width, settings.video_height, settings.fps
    frames = max(1, round(shot.duration * fps))
    pre, vf = motion_filter(shot.motion, w, h, frames, fps)
    run_ffmpeg([*pre, "-i", str(image), "-vf", vf + ",format=yuv420p,setsar=1", "-frames:v", str(frames),
                "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", str(out_path)],
               settings.ffmpeg_bin)
    return out_path
