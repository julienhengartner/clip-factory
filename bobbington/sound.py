"""Bobbington audio identity – every sound is synthesised here (original work, no licence issues).

theme          pompous brass-band fanfare in B-flat major + deflating trombone 'wah-wah'
fanfare_short  two-bar triumphant brass hit
sting          two-note tuba button + teacup clink (end of every episode)
sfx            gavel, stamp, clock_tick, murmur, birds, glass_clink, record_scratch, whoosh
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
A4 = 440.0


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(SR * seconds)) / SR


def note_freq(name: str) -> float:
    names = {"C": -9, "C#": -8, "Db": -8, "D": -7, "Eb": -6, "D#": -6, "E": -5, "F": -4, "F#": -3, "Gb": -3,
             "G": -2, "Ab": -1, "G#": -1, "A": 0, "Bb": 1, "A#": 1, "B": 2}
    pitch, octave = name[:-1], int(name[-1])
    return A4 * 2 ** ((names[pitch] + 12 * (octave - 4)) / 12)


def adsr(n: int, a=0.02, d=0.08, s=0.75, r=0.12) -> np.ndarray:
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    env = np.ones(n) * s
    env[:a] = np.linspace(0, 1, a, endpoint=False) if a else env[:a]
    env[a:a + d] = np.linspace(1, s, max(1, min(d, n - a)))[: len(env[a:a + d])]
    if r and n > r:
        env[-r:] = np.linspace(s, 0, r)
    return env


def brass(freq: float, seconds: float, vibrato=4.5, bright=1.0) -> np.ndarray:
    t = _t(seconds)
    f = freq * (1 + 0.004 * np.sin(2 * np.pi * vibrato * t) * np.clip(t * 3, 0, 1))
    phase = 2 * np.pi * np.cumsum(f) / SR
    # brassy: odd+even harmonics, brightness grows with the attack
    swell = np.clip(t / 0.08, 0, 1)
    sig = sum((0.6 ** k) * np.sin(k * phase) * (swell ** (k * 0.3 / bright)) for k in range(1, 9))
    return sig * adsr(len(t), 0.03, 0.1, 0.8, 0.1)


def chord(notes: list[str], seconds: float, **kw) -> np.ndarray:
    return sum(brass(note_freq(n), seconds, **kw) for n in notes) / len(notes)


def timpani(seconds=0.6, freq=73.4) -> np.ndarray:
    t = _t(seconds)
    return (np.sin(2 * np.pi * freq * t) + 0.3 * np.random.default_rng(1).normal(0, 1, len(t)) * np.exp(-t * 40)) * np.exp(-t * 5)


def cymbal(seconds=1.2) -> np.ndarray:
    t = _t(seconds)
    noise = np.random.default_rng(2).normal(0, 1, len(t))
    hp = np.diff(noise, prepend=0)
    return hp * np.exp(-t * 3.5) * 0.35


def place(track: np.ndarray, clip: np.ndarray, at: float, gain=1.0) -> None:
    i = int(at * SR)
    j = min(len(track), i + len(clip))
    if i < len(track):
        track[i:j] += clip[: j - i] * gain


def normalise(x: np.ndarray, peak=0.89) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


# --- music -----------------------------------------------------------------------------------
def theme() -> np.ndarray:
    """4 pompous bars (Bb major, 'I – IV – V – I' with a grand pause) then a deflating trombone."""
    beat = 0.32
    out = np.zeros(int(SR * 2.6))
    melody = [("Bb4", 0, 1.5), ("D5", 1.5, 0.5), ("F5", 2, 1), ("Eb5", 3, 1), ("D5", 4, 1), ("C5", 5, 1)]
    for n, b, l in melody:
        place(out, brass(note_freq(n), l * beat * 0.95, bright=1.3), b * beat, 0.55)
    for notes, b in ((["Bb2", "F3", "D4"], 0), (["Eb3", "G3", "Bb3"], 3), (["F3", "A3", "C4"], 4.5)):
        place(out, chord(notes, 1.4 * beat), b * beat, 0.45)
    place(out, timpani(), 0, 0.6)
    place(out, cymbal(), 0, 1.0)
    # the deflating 'wah-wah' – the joke of the theme
    t = _t(0.75)
    f = note_freq("F3") * 2 ** (-np.clip(t / 0.75, 0, 1) * 7 / 12)
    wah = sum((0.55 ** k) * np.sin(k * 2 * np.pi * np.cumsum(f) / SR) for k in range(1, 7))
    wah *= (0.6 + 0.4 * np.sin(2 * np.pi * 4.0 * t)) * adsr(len(t), 0.02, 0.1, 0.9, 0.2)
    place(out, wah, 6.2 * beat, 0.6)
    return normalise(out)


def fanfare_short() -> np.ndarray:
    beat = 0.22
    out = np.zeros(int(SR * 1.6))
    for i, n in enumerate(["F4", "Bb4", "D5", "F5"]):
        place(out, brass(note_freq(n), beat * (3 if i == 3 else 0.9), bright=1.4), i * beat, 0.5)
    place(out, chord(["Bb3", "D4", "F4"], beat * 3), 3 * beat, 0.4)
    place(out, cymbal(0.9), 3 * beat, 0.8)
    return normalise(out)


def sting() -> np.ndarray:
    out = np.zeros(int(SR * 1.5))
    for i, n in enumerate(["F2", "Bb1"]):
        t = _t(0.35)
        f = note_freq(n)
        tone = sum((0.5 ** k) * np.sin(k * 2 * np.pi * f * t) for k in range(1, 6)) * adsr(len(t), 0.01, 0.05, 0.8, 0.12)
        place(out, tone, i * 0.38, 0.8)
    place(out, glass_clink(), 0.95, 0.7)
    return normalise(out)


# --- sound effects ---------------------------------------------------------------------------
def gavel() -> np.ndarray:
    t = _t(0.35)
    knock = np.sin(2 * np.pi * 180 * t) * np.exp(-t * 30) + 0.5 * np.sin(2 * np.pi * 95 * t) * np.exp(-t * 18)
    click = np.random.default_rng(3).normal(0, 1, len(t)) * np.exp(-t * 120) * 0.6
    return normalise(knock + click)


def stamp() -> np.ndarray:
    t = _t(0.22)
    thud = np.sin(2 * np.pi * 120 * t) * np.exp(-t * 35)
    slap = np.random.default_rng(4).normal(0, 1, len(t)) * np.exp(-t * 90) * 0.8
    return normalise(thud + slap, 0.8)


def clock_tick(seconds=4.0) -> np.ndarray:
    out = np.zeros(int(SR * seconds))
    t = _t(0.03)
    tick = np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 300)
    tock = np.sin(2 * np.pi * 1700 * t) * np.exp(-t * 300)
    for i in range(int(seconds)):
        place(out, tick if i % 2 == 0 else tock, i * 1.0, 0.6)
    return out


def _lowpass(x: np.ndarray, alpha: float) -> np.ndarray:
    y = np.zeros_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # small one-pole filter; inputs here are short
        acc += alpha * (v - acc)
        y[i] = acc
    return y


def murmur(seconds=4.0) -> np.ndarray:
    rng = np.random.default_rng(5)
    t = _t(seconds)
    noise = rng.normal(0, 1, len(t))
    # 'voices': band-limited noise with syllable-like amplitude modulation
    shaped = np.convolve(noise, np.ones(30) / 30, mode="same") - np.convolve(noise, np.ones(300) / 300, mode="same")
    mod = 0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 3.1 * t) * np.sin(2 * np.pi * 1.3 * t + 1))
    fade = np.clip(t / 0.5, 0, 1) * np.clip((seconds - t) / 0.8, 0, 1)
    return normalise(shaped * mod * fade, 0.5)


def birds(seconds=8.0) -> np.ndarray:
    rng = np.random.default_rng(6)
    out = np.zeros(int(SR * seconds))
    for _ in range(int(seconds * 1.6)):
        dur = rng.uniform(0.05, 0.14)
        t = _t(dur)
        f0 = rng.uniform(2800, 4200)
        chirp = np.sin(2 * np.pi * (f0 + rng.uniform(-900, 900) * t / dur) * t) * np.sin(np.pi * t / dur)
        place(out, chirp, rng.uniform(0, seconds - dur), rng.uniform(0.2, 0.5))
    return out


def glass_clink() -> np.ndarray:
    t = _t(0.6)
    sig = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, a, d in
              ((2637, 1.0, 9), (3951, 0.6, 12), (5274, 0.35, 16), (7040, 0.2, 22)))
    return normalise(sig, 0.7)


def record_scratch() -> np.ndarray:
    t = _t(0.45)
    rng = np.random.default_rng(7)
    f = 600 + 900 * np.sin(2 * np.pi * 3.2 * t)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    grit = rng.normal(0, 1, len(t)) * 0.4
    return normalise((tone + grit) * np.exp(-t * 3) * np.clip(t / 0.01, 0, 1), 0.7)


def whoosh() -> np.ndarray:
    t = _t(0.5)
    noise = np.random.default_rng(8).normal(0, 1, len(t))
    env = np.sin(np.pi * t / 0.5) ** 2
    return normalise(np.convolve(noise, np.ones(12) / 12, mode="same") * env, 0.5)


LIBRARY = {"theme": theme, "fanfare_short": fanfare_short, "sting": sting, "gavel": gavel, "stamp": stamp,
           "clock_tick": clock_tick, "murmur": murmur, "birds": birds, "glass_clink": glass_clink,
           "record_scratch": record_scratch, "whoosh": whoosh}
SUSTAINED = {"clock_tick", "murmur", "birds"}   # accept a duration


def write_wav(path: Path, samples: np.ndarray) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    return path


def render(name: str, duration: float | None = None) -> np.ndarray:
    fn = LIBRARY[name]
    return fn(duration) if (name in SUSTAINED and duration) else fn()


def build_library(out_dir: Path) -> dict[str, Path]:
    """Writes every sound once (for listening/checking); production renders on demand."""
    return {name: write_wav(Path(out_dir) / f"{name}.wav", render(name)) for name in LIBRARY}
