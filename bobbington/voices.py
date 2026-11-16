"""Character voices with Piper (free, offline, British English models).

Piper (GPL-3.0) is invoked as a separate program, never imported, so it stays a stand-alone tool.
Voice models live outside the repository (BBOB_PIPER_VOICES_DIR). Licences of the used models:
  en_GB-northern_english_male (CC BY-SA 4.0, OpenSLR 83), en_GB-vctk (CC BY 4.0),
  en_GB-alba (CC BY 4.0), en_GB-cori (public domain / LibriVox).
Results are cached by (text, voice settings) so re-runs and length fitting cost nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

from bobbington.bible import CAST

_CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
VOICE_CREDITS = {
    "en_GB-northern_english_male-medium": "Piper voice 'northern_english_male' – OpenSLR 83 (CC BY-SA 4.0)",
    "en_GB-vctk-medium": "Piper voice 'vctk' – CSTR VCTK Corpus, University of Edinburgh (CC BY 4.0)",
    "en_GB-alba-medium": "Piper voice 'alba' – University of Edinburgh (CC BY 4.0)",
    "en_GB-cori-medium": "Piper voice 'cori' – LibriVox recordings (public domain)",
}


def piper_binary() -> str:
    cand = Path(sys.prefix) / ("Scripts/piper.exe" if os.name == "nt" else "bin/piper")
    return str(cand) if cand.exists() else "piper"


class VoiceBank:
    def __init__(self, voices_dir: Path, cache_dir: Path):
        self.voices_dir = Path(voices_dir)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def model_path(self, model: str) -> Path:
        p = self.voices_dir / f"{model}.onnx"
        if not p.is_file():
            raise FileNotFoundError(f"Piper voice model missing: {p} (see README, section 'Voices')")
        return p

    def speaker_id(self, model: str, speaker: str | None) -> int | None:
        if speaker is None:
            return None
        cfg = json.loads((self.voices_dir / f"{model}.onnx.json").read_text(encoding="utf-8"))
        mapping = cfg.get("speaker_id_map", {})
        if speaker not in mapping:
            raise ValueError(f"speaker {speaker} not in {model}")
        return int(mapping[speaker])

    def synthesize(self, character: str, text: str) -> Path:
        v = CAST[character]["voice"]
        key = hashlib.sha256(json.dumps([text, v], sort_keys=True).encode()).hexdigest()[:20]
        out = self.cache_dir / f"{character}_{key}.wav"
        if out.is_file():
            return out
        cmd = [piper_binary(), "-m", str(self.model_path(v["model"])), "-f", str(out),
               "--length-scale", str(v["length_scale"]), "--noise-scale", str(v["noise_scale"]),
               "--noise-w-scale", str(v["noise_w"]), "--volume", str(v.get("volume", 1.0))]
        sid = self.speaker_id(v["model"], v.get("speaker"))
        if sid is not None:
            cmd += ["-s", str(sid)]
        proc = subprocess.run(cmd, input=text, capture_output=True, text=True, encoding="utf-8",
                              creationflags=_CREATIONFLAGS, timeout=180, check=False)
        if proc.returncode != 0 or not out.is_file():
            raise RuntimeError(f"Piper failed for {character}: {proc.stderr.strip()[-400:]}")
        return out


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def speech_bounds(samples: np.ndarray, sr: int, threshold: float = 0.02) -> tuple[float, float]:
    """First and last moment with audible speech (seconds) – used to trim Piper's padding for timing."""
    win = max(1, int(sr * 0.01))
    n = len(samples) // win
    if n == 0:
        return 0.0, len(samples) / sr
    rms = np.sqrt((samples[: n * win].reshape(n, win) ** 2).mean(axis=1))
    loud = np.where(rms > threshold)[0]
    if len(loud) == 0:
        return 0.0, len(samples) / sr
    return loud[0] * win / sr, (loud[-1] + 1) * win / sr


def mouth_envelope(samples: np.ndarray, sr: int, fps: int) -> list[float]:
    """Mouth opening per video frame (0..1) from the speech loudness – drives the lip sync."""
    hop = sr / fps
    n = int(np.ceil(len(samples) / hop))
    vals = []
    for i in range(n):
        seg = samples[int(i * hop): int((i + 1) * hop)]
        vals.append(float(np.sqrt((seg ** 2).mean())) if len(seg) else 0.0)
    arr = np.array(vals)
    peak = np.percentile(arr, 95) if arr.max() > 0 else 1.0
    arr = np.clip(arr / max(peak, 1e-6), 0, 1)
    arr[arr < 0.12] = 0.0
    return [round(float(x), 3) for x in arr]
