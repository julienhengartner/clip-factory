"""Kostenlose lokale deutsche Sprachausgabe über Windows (System.Speech, Stimme z. B. "Microsoft Hedda").

Liefert WAV (44,1 kHz mono) plus Wort-Zeitstempel. SAPI meldet AudioPosition so, als wäre die Ausgabe
16 kHz/16 bit – unabhängig vom tatsächlichen Format. Die Werte werden deshalb mit 16000/44100 skaliert
(empirisch verifiziert gegen ffmpeg-silencedetect). Unplausible Werte -> proportionale Verteilung.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from core.errors import ExternalApiError, NotConfiguredError
from core.text import words as split_words
from storage.models import VoiceClip, WordTiming
from video_engine.ffmpeg import probe_duration

SCRIPT = Path(__file__).parent / "scripts" / "sapi_tts.ps1"
SAPI_TIME_BASE_HZ = 16000
OUTPUT_HZ = 44100
_CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def is_available() -> bool:
    return os.name == "nt" and shutil.which("powershell") is not None


def word_timings_from_sapi(text: str, events: list[dict], duration_s: float) -> list[WordTiming]:
    """Wandelt SAPI-Ereignisse (t in ms, pos, len) in korrigierte Wortzeiten um."""
    factor = SAPI_TIME_BASE_HZ / OUTPUT_HZ
    raw = []
    for e in events:
        token = text[e["pos"]: e["pos"] + e["len"]]
        clean = " ".join(split_words(token))
        if clean:
            raw.append((clean, e["t"] / 1000.0 * factor))
    plausible = bool(raw) and all(b[1] >= a[1] for a, b in zip(raw, raw[1:])) and raw[-1][1] < duration_s
    if not plausible:
        return proportional_timings(text, duration_s)
    out = []
    for i, (w, start) in enumerate(raw):
        end = raw[i + 1][1] if i + 1 < len(raw) else min(duration_s, start + max(0.25, 0.08 * len(w)))
        out.append(WordTiming(word=w, start=round(start, 3), end=round(max(end, start + 0.05), 3)))
    return out


def proportional_timings(text: str, duration_s: float, lead_s: float = 0.1, tail_s: float = 0.15) -> list[WordTiming]:
    """Notlösung: Wortzeiten proportional zur Zeichenlänge verteilen."""
    ws = split_words(text)
    if not ws:
        return []
    span = max(0.1, duration_s - lead_s - tail_s)
    total = sum(len(w) + 1 for w in ws)
    t, out = lead_s, []
    for w in ws:
        d = span * (len(w) + 1) / total
        out.append(WordTiming(word=w, start=round(t, 3), end=round(t + d, 3)))
        t += d
    return out


class WindowsTTS:
    provider = "windows"

    def __init__(self, voice: str, rate: int = 0, ffprobe_bin: str = "ffprobe", timeout_s: float = 300):
        self.voice, self.rate, self.ffprobe_bin, self.timeout_s = voice, max(-10, min(10, rate)), ffprobe_bin, timeout_s

    def synthesize_batch(self, items: list[tuple[str, Path]]) -> list[VoiceClip]:
        """Synthetisiert mehrere Texte in einem PowerShell-Aufruf (spart Startzeit)."""
        if not is_available():
            raise NotConfiguredError("Windows-Sprachausgabe", ["Windows mit PowerShell und System.Speech"])
        if not items:
            return []
        work = Path(tempfile.mkdtemp(prefix="bbob_tts_"))
        try:
            job_items = []
            for i, (text, wav) in enumerate(items):
                tf = work / f"{i}.txt"
                tf.write_text(text, encoding="utf-8")
                Path(wav).parent.mkdir(parents=True, exist_ok=True)
                job_items.append({"text_file": str(tf), "wav": str(Path(wav).resolve()), "timings": str(work / f"{i}.json")})
            job = work / "job.json"
            job.write_text(json.dumps({"voice": self.voice, "rate": self.rate, "items": job_items}), encoding="utf-8")
            proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                   "-File", str(SCRIPT), "-JobFile", str(job)], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=self.timeout_s,
                                  creationflags=_CREATIONFLAGS, check=False)
            if proc.returncode != 0:
                raise ExternalApiError("windows_tts", (proc.stderr or proc.stdout).strip()[-500:])
            clips = []
            for (text, wav), ji in zip(items, job_items):
                duration = probe_duration(wav, self.ffprobe_bin)
                events = json.loads(Path(ji["timings"]).read_text(encoding="utf-8-sig") or "[]")
                clips.append(VoiceClip(path=str(wav), duration_s=round(duration, 3), provider=self.provider,
                                       words=word_timings_from_sapi(text, events, duration)))
            return clips
        finally:
            shutil.rmtree(work, ignore_errors=True)
