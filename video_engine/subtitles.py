"""Untertitel-Dateien: ASS (eingebrannt, mit Wort-für-Wort-Hervorhebung) und SRT (Archiv/Upload)."""
from __future__ import annotations

from pathlib import Path

from config import Settings
from storage.models import SubtitleCue


def _ts_ass(t: float) -> str:
    cs = max(0, int(round(t * 100)))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ts_srt(t: float) -> str:
    ms = max(0, int(round(t * 1000)))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _esc(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def write_ass(cues: list[SubtitleCue], path: Path, settings: Settings) -> Path:
    w, h = settings.video_width, settings.video_height
    size = max(10, round(h * 0.043))
    outline = max(1, round(h * 0.0032))
    margin_v = round(h * 0.25)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Bob,{settings.subtitle_font_name},{size},&H0000D7FF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{outline},{max(1, outline // 2)},2,{round(w * 0.08)},{round(w * 0.08)},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for cue in cues:
        parts = []
        for i, wd in enumerate(cue.words):
            nxt = cue.words[i + 1].start if i + 1 < len(cue.words) else cue.end
            k = max(1, int(round((nxt - wd.start) * 100)))
            parts.append(f"{{\\k{k}}}{_esc(wd.word.upper())}")
        lines.append(f"Dialogue: 0,{_ts_ass(cue.start)},{_ts_ass(cue.end)},Bob,,0,0,0,,{' '.join(parts)}")
    Path(path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return Path(path)


def write_srt(cues: list[SubtitleCue], path: Path) -> Path:
    blocks = [f"{i}\n{_ts_srt(c.start)} --> {_ts_srt(c.end)}\n{c.text}\n" for i, c in enumerate(cues, 1)]
    Path(path).write_text("\n".join(blocks), encoding="utf-8")
    return Path(path)
