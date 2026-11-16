"""Subtitle Agent: erzeugt wortgenau synchronisierte Untertitel (TikTok-Stil: 1–3 Wörter pro Einblendung).

Einblendungen enden an Satzgrenzen und Sprechpausen, damit nie zwei Sätze in einer Zeile stehen.
"""
from __future__ import annotations

import re
from pathlib import Path

from agents.base import Agent
from core.text import words as split_words
from storage.models import Scene, SubtitleCue, WordTiming
from video_engine.subtitles import write_ass, write_srt

MAX_WORDS = 3
MAX_CHARS = 20
GAP_BREAK_S = 0.35
_TOKEN = re.compile(r"[0-9A-Za-zÄÖÜäöüßÀ-ÿ]+(?:[-'’][0-9A-Za-zÄÖÜäöüßÀ-ÿ]+)*")


def sentence_end_flags(text: str) -> list[bool]:
    """Für jedes Wort im Text: folgt darauf ein Satz- oder Teilsatzende (. ! ? : ; – ,)?"""
    flags = []
    for m in _TOKEN.finditer(text):
        after = text[m.end():m.end() + 3]
        flags.append(bool(re.match(r"\s*[.!?:;–,]", after)))
    return flags


def build_cues(scenes: list[Scene]) -> list[SubtitleCue]:
    words: list[WordTiming] = []
    breaks: list[bool] = []
    for sc in scenes:
        flags = sentence_end_flags(sc.text)
        aligned = len(flags) == len(sc.words) and [w.word for w in sc.words] == split_words(sc.text)
        for k, w in enumerate(sc.words):
            words.append(WordTiming(word=w.word, start=round(sc.start_s + w.start, 3), end=round(sc.start_s + w.end, 3)))
            breaks.append((flags[k] if aligned else False) or k == len(sc.words) - 1)
    cues: list[SubtitleCue] = []
    buf: list[WordTiming] = []
    for i, w in enumerate(words):
        if buf and (len(buf) >= MAX_WORDS or len(" ".join(x.word for x in buf + [w])) > MAX_CHARS
                    or w.start - buf[-1].end > GAP_BREAK_S):
            cues.append(SubtitleCue(start=buf[0].start, end=buf[-1].end, words=buf))
            buf = []
        buf.append(w)
        if breaks[i]:
            cues.append(SubtitleCue(start=buf[0].start, end=buf[-1].end, words=buf))
            buf = []
    if buf:
        cues.append(SubtitleCue(start=buf[0].start, end=buf[-1].end, words=buf))
    # Mindestanzeigedauer, ohne in die nächste Einblendung zu ragen; kleine Lücken schliessen
    for i, c in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else c.end + 0.4
        c.end = round(max(c.end, min(nxt, c.start + 0.5)), 3)
        if nxt - c.end < 0.25:
            c.end = round(nxt, 3)
    return cues


class SubtitleAgent(Agent):
    name = "subtitles"

    def build(self, scenes: list[Scene], out_dir: Path) -> tuple[list[SubtitleCue], Path, Path]:
        cues = build_cues(scenes)
        ass = write_ass(cues, out_dir / "subtitles.ass", self.s)
        srt = write_srt(cues, out_dir / "subtitles.srt")
        return cues, ass, srt
