"""Technische Videoanalyse mit ffprobe/FFmpeg (ein Analysedurchlauf für alle Detektoren)."""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from config import Settings
from video_engine.ffmpeg import probe, run_ffmpeg_capture


class MediaAnalysis(BaseModel):
    duration_s: float
    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    pix_fmt: str | None = None
    audio_channels: int | None = None
    integrated_lufs: float | None = None
    true_peak_dbfs: float | None = None
    silences: list[tuple[float, float]] = Field(default_factory=list)   # (start, dauer)
    freezes: list[tuple[float, float]] = Field(default_factory=list)
    blacks: list[tuple[float, float]] = Field(default_factory=list)

    @property
    def longest_silence_s(self) -> float:
        return max((d for _, d in self.silences), default=0.0)

    @property
    def longest_freeze_s(self) -> float:
        return max((d for _, d in self.freezes), default=0.0)


def _fps(rate: str | None) -> float | None:
    if not rate or "/" not in rate:
        return None
    n, d = rate.split("/")
    return float(n) / float(d) if float(d) else None


def _pairs(log: str, start_key: str, dur_key: str, end_key: str | None = None) -> list[tuple[float, float]]:
    starts = [float(x) for x in re.findall(rf"{start_key}:\s*(-?[\d.]+)", log)]
    durs = [float(x) for x in re.findall(rf"{dur_key}:\s*([\d.]+)", log)]
    return list(zip(starts, durs))


def parse_analysis_log(log: str) -> dict:
    out: dict = {
        "silences": _pairs(log, "silence_start", "silence_duration"),
        "freezes": _pairs(log, r"lavfi\.freezedetect\.freeze_start", r"lavfi\.freezedetect\.freeze_duration"),
        "blacks": [(float(s), float(d)) for s, _, d in
                   re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)", log)],
    }
    summary = log.split("Summary:")[-1] if "Summary:" in log else ""
    m = re.search(r"I:\s*(-?[\d.]+|-inf)\s*LUFS", summary)
    if m and m.group(1) != "-inf":
        out["integrated_lufs"] = float(m.group(1))
    m = re.search(r"True peak:\s*Peak:\s*(-?[\d.]+|-inf)\s*dBFS", summary, re.S)
    if m and m.group(1) != "-inf":
        out["true_peak_dbfs"] = float(m.group(1))
    return out


def analyze(path: Path, settings: Settings) -> MediaAnalysis:
    info = probe(path, settings.ffprobe_bin)
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
    a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), {})
    log = run_ffmpeg_capture([
        "-i", str(path),
        "-vf", "freezedetect=n=0.001:d=2.0,blackdetect=d=0.5:pix_th=0.08",
        "-af", "silencedetect=n=-45dB:d=0.8,ebur128=peak=true:framelog=verbose",
        "-f", "null", "-"], settings.ffmpeg_bin)
    parsed = parse_analysis_log(log)
    return MediaAnalysis(
        duration_s=float(info.get("format", {}).get("duration", 0.0)),
        video_codec=v.get("codec_name"), audio_codec=a.get("codec_name"), width=v.get("width"),
        height=v.get("height"), fps=_fps(v.get("avg_frame_rate") or v.get("r_frame_rate")), pix_fmt=v.get("pix_fmt"),
        audio_channels=a.get("channels"), **parsed)
