"""Dünne, sichere Hülle um FFmpeg/ffprobe (keine Shell, Argumentlisten)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

_CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class FFmpegError(RuntimeError):
    pass


class FFmpegNotFoundError(FFmpegError):
    pass


def resolve_binary(name: str) -> str:
    """Gibt den vollständigen Pfad zu ffmpeg/ffprobe zurück oder wirft FFmpegNotFoundError."""
    candidate = Path(name)
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    if not found:
        raise FFmpegNotFoundError(
            f"'{name}' wurde nicht gefunden. FFmpeg installieren und zum PATH hinzufügen "
            f"oder BBOB_FFMPEG_BIN / BBOB_FFPROBE_BIN setzen."
        )
    return found


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, creationflags=_CREATIONFLAGS, check=False)
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"Zeitüberschreitung nach {timeout}s: {cmd[0]}") from exc


def run_ffmpeg(args: list[str], ffmpeg_bin: str = "ffmpeg", timeout: float = 600) -> None:
    cmd = [resolve_binary(ffmpeg_bin), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    proc = _run(cmd, timeout)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise FFmpegError(f"FFmpeg fehlgeschlagen (Code {proc.returncode}):\n{tail}")


def run_ffmpeg_capture(args: list[str], ffmpeg_bin: str = "ffmpeg", timeout: float = 900) -> str:
    """Wie run_ffmpeg, liefert aber das Info-Log (stderr) – für Analysefilter."""
    cmd = [resolve_binary(ffmpeg_bin), "-hide_banner", "-nostats", "-loglevel", "info", "-nostdin", "-y", *args]
    proc = _run(cmd, timeout)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise FFmpegError(f"FFmpeg-Analyse fehlgeschlagen (Code {proc.returncode}):\n{tail}")
    return proc.stderr


def probe(path: str | Path, ffprobe_bin: str = "ffprobe") -> dict:
    cmd = [resolve_binary(ffprobe_bin), "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    proc = _run(cmd, 60)
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe fehlgeschlagen für {path}: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def probe_duration(path: str | Path, ffprobe_bin: str = "ffprobe") -> float:
    info = probe(path, ffprobe_bin)
    try:
        return float(info["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FFmpegError(f"Keine Laufzeit ermittelbar für {path}") from exc


def ffmpeg_version(ffmpeg_bin: str = "ffmpeg") -> str:
    proc = _run([resolve_binary(ffmpeg_bin), "-version"], 30)
    return proc.stdout.splitlines()[0] if proc.stdout else "unbekannt"


def escape_filter_value(path: str | Path) -> str:
    """Pfad für FFmpeg-Filterargumente escapen (Windows: Backslashes und Laufwerks-Doppelpunkt)."""
    p = str(Path(path).resolve()).replace("\\", "/")
    return p.replace(":", r"\:").replace("'", r"\'")
