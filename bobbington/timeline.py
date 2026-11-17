"""Timeline: turns an episode + real voice recordings into frame-exact instructions for Blender,
a full audio mix and timed English subtitles.

Length fitting (absolute priority): the real audio length decides. Below the minimum, extension lines from
the script are added; above the ideal maximum, optional lines are dropped. Never silence or still frames.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from bobbington import sound
from bobbington.episode import Episode, Line, Shot
from bobbington.voices import VoiceBank, mouth_envelope, read_wav, speech_bounds

LEAD_S = 0.30
COLD_OPEN_LEAD_S = 0.12
TAIL_S = 0.45
FINAL_TAIL_S = 1.7      # room for the sting


class TimedLine(BaseModel):
    speaker: str
    text: str
    action: str
    emotion: str
    start: float          # seconds (episode time), start of the audio file
    end: float
    speech_start: float
    speech_end: float
    audio: str
    start_frame: int
    end_frame: int
    mouth: list[float]


class TimedShot(BaseModel):
    id: str
    set: str
    cast: dict[str, str]
    camera: dict
    on_screen: dict[str, str] = Field(default_factory=dict)
    start: float
    end: float
    start_frame: int
    end_frame: int
    lines: list[TimedLine] = Field(default_factory=list)


class SubtitleCue(BaseModel):
    start: float
    end: float
    text: str
    speaker: str


class Timeline(BaseModel):
    episode_id: str
    title: str
    fps: int
    width: int
    height: int
    duration: float
    total_frames: int
    shots: list[TimedShot]
    subtitles: list[SubtitleCue]
    adjustments: list[str] = Field(default_factory=list)
    city: dict = Field(default_factory=dict)   # base scene + draft city version + story events


def chunk_text(text: str, max_words: int = 5, max_chars: int = 30) -> list[str]:
    words, chunks, cur = text.split(), [], []
    for w in words:
        if cur and (len(cur) >= max_words or len(" ".join(cur + [w])) > max_chars):
            chunks.append(" ".join(cur))
            cur = []
        cur.append(w)
        if w[-1] in ".!?…" and len(cur) >= 2:
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def apply_extensions(ep: Episode, count: int) -> Episode:
    shots = [s.model_copy(deep=True) for s in ep.shots]
    for ext in ep.extensions[:count]:
        shot = next(s for s in shots if s.id == ext.after_shot)
        if ext.speaker not in shot.cast:
            shot.cast[ext.speaker] = next(iter(shot.cast.values()), "centre")
        shot.lines.append(Line(speaker=ext.speaker, text=ext.text, action=ext.action, emotion=ext.emotion))
    return ep.model_copy(update={"shots": shots})


def drop_optional(ep: Episode) -> Episode:
    shots = []
    for s in ep.shots:
        kept = [l for l in s.lines if not l.optional]
        shots.append(s.model_copy(update={"lines": kept}) if kept or s.duration else s)
    return ep.model_copy(update={"shots": shots})


class TimelineBuilder:
    def __init__(self, voices: VoiceBank, fps: int = 24, width: int = 1080, height: int = 1920):
        self.voices, self.fps, self.width, self.height = voices, fps, width, height

    def _frame(self, t: float) -> int:
        return int(round(t * self.fps))

    def build(self, ep: Episode) -> Timeline:
        t = 0.0
        shots: list[TimedShot] = []
        subs: list[SubtitleCue] = []
        for i, shot in enumerate(ep.shots):
            start = t
            timed_lines: list[TimedLine] = []
            if shot.lines:
                t += COLD_OPEN_LEAD_S if i == 0 else LEAD_S
                for k, line in enumerate(shot.lines):
                    if k > 0 or line.pause_before > 0.3:
                        t += line.pause_before
                    wav = self.voices.synthesize(line.speaker, line.text)
                    samples, sr = read_wav(wav)
                    dur = len(samples) / sr
                    a, b = speech_bounds(samples, sr)
                    env = mouth_envelope(samples, sr, self.fps)
                    timed_lines.append(TimedLine(
                        speaker=line.speaker, text=line.text, action=line.action, emotion=line.emotion, start=t,
                        end=t + dur, speech_start=t + a, speech_end=t + b, audio=str(wav),
                        start_frame=self._frame(t), end_frame=self._frame(t + dur), mouth=env))
                    # subtitles proportional to characters inside the audible speech span
                    chunks = chunk_text(line.text)
                    total_chars = sum(len(c) for c in chunks) or 1
                    ct = t + a
                    for c in chunks:
                        d = (b - a) * len(c) / total_chars
                        subs.append(SubtitleCue(start=round(ct, 3), end=round(ct + d, 3), text=c, speaker=line.speaker))
                        ct += d
                    t += dur
                t += FINAL_TAIL_S if i == len(ep.shots) - 1 else TAIL_S
            else:
                t += shot.duration or 2.0
            shots.append(TimedShot(id=shot.id, set=shot.set, cast=shot.cast,
                                   camera=shot.camera.model_dump(by_alias=True), on_screen=shot.on_screen,
                                   start=start, end=t, start_frame=self._frame(start), end_frame=self._frame(t),
                                   lines=timed_lines))
        for a, b in zip(subs, subs[1:]):  # no overlaps, small gaps closed
            if b.start - a.end < 0.12:
                a.end = max(a.start + 0.2, b.start - 0.01)
        return Timeline(episode_id=ep.id, title=ep.title, fps=self.fps, width=self.width, height=self.height,
                        duration=round(t, 3), total_frames=self._frame(t), shots=shots, subtitles=subs)

    def fit(self, ep: Episode, min_s: float = 60.0, ideal_max_s: float = 75.0, hard_max_s: float = 80.0,
            margin_s: float = 1.0) -> tuple[Episode, Timeline]:
        """Adjusts the script until the REAL duration is in range."""
        notes = []
        current = ep
        tl = self.build(current)
        n_ext = 0
        while tl.duration < min_s + margin_s and n_ext < len(ep.extensions):
            n_ext += 1
            current = apply_extensions(ep, n_ext)
            tl = self.build(current)
            notes.append(f"too short – added extension line {n_ext} -> {tl.duration:.2f}s")
        if tl.duration > ideal_max_s:
            trimmed = drop_optional(current)
            tl2 = self.build(trimmed)
            if tl2.duration >= min_s + margin_s:
                current, tl = trimmed, tl2
                notes.append(f"over ideal – dropped optional lines -> {tl.duration:.2f}s")
        if tl.duration < min_s:
            raise ValueError(f"Episode too short ({tl.duration:.2f}s) even with all extensions – script needs more material")
        if tl.duration > hard_max_s:
            raise ValueError(f"Episode too long ({tl.duration:.2f}s) – script must be cut")
        tl.adjustments = notes
        return current, tl


# --- audio mix ---------------------------------------------------------------------------------
def mix_audio(ep: Episode, tl: Timeline, out_wav: Path) -> Path:
    total = np.zeros(int(math.ceil(tl.duration * sound.SR)) + sound.SR)
    shots_by_id = {s.id: s for s in ep.shots}
    for ts in tl.shots:
        src: Shot = shots_by_id[ts.id]
        for line in ts.lines:
            x, sr = read_wav(Path(line.audio))
            if sr != sound.SR:  # simple resample (linear) – Piper outputs 22.05 kHz
                idx = np.arange(0, len(x), sr / sound.SR)
                x = np.interp(idx, np.arange(len(x)), x)
            sound.place(total, x, line.start, 1.0)
        cues = list(src.sfx) + ([src.music] if src.music else [])
        for cue in cues:
            if cue.at_line_end is not None and cue.at_line_end < len(ts.lines):
                at = ts.lines[cue.at_line_end].speech_end + 0.05
            else:
                at = ts.start + (cue.at or 0.0)
            clip = sound.render(cue.name, cue.duration)
            for r in range(cue.repeat):
                sound.place(total, clip, at + r * (len(clip) / sound.SR + cue.gap) if cue.repeat > 1 else at,
                            cue.volume * (0.5 if cue.name in ("theme", "fanfare_short", "sting") else 0.6))
    total = total[: int(tl.duration * sound.SR)]
    return sound.write_wav(out_wav, sound.normalise(total, 0.9))


def write_timeline(tl: Timeline, path: Path) -> Path:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(tl.model_dump_json(indent=1), encoding="utf-8")
    return Path(path)


def load_timeline(path: Path) -> Timeline:
    return Timeline.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
