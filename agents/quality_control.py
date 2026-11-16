"""Quality Control Agent: prüft jedes fertige Video. Fehler (severity=error) verhindern jede Veröffentlichung.

Geprüft werden u. a.: Länge per ffprobe (>= 60 s Pflicht, <= 80 s), Format 1080x1920/H.264/AAC/30 fps,
Lautheit, keine langen Pausen (kein künstliches Strecken), keine Standbilder, keine Schwarzbilder,
Untertitel vollständig und synchron, Hook in den ersten Sekunden, verifizierte Quellen.
"""
from __future__ import annotations

from pathlib import Path

from agents.base import Agent
from core.text import word_count
from storage.models import QCCheck, QCReport, Scene, Script, SubtitleCue
from video_engine.duration import LengthVerdict, evaluate_length
from video_engine.quality_check import MediaAnalysis, analyze

LUFS_RANGE = (-18.0, -10.0)
MAX_SILENCE_S = 1.5
MAX_FREEZE_S = 2.5
HOOK_MAX_WORDS = 12
HOOK_START_MAX_S = 1.0
HOOK_END_MAX_S = 4.0


class QualityControlAgent(Agent):
    name = "quality_control"

    def check(self, video: Path, scenes: list[Scene], script: Script, cues: list[SubtitleCue],
              sources_verified: bool) -> QCReport:
        a = analyze(video, self.s)
        return self.evaluate(a, scenes, script, cues, sources_verified)

    def evaluate(self, a: MediaAnalysis, scenes: list[Scene], script: Script, cues: list[SubtitleCue],
                 sources_verified: bool) -> QCReport:
        s, checks = self.s, []
        length = evaluate_length(a.duration_s, s)
        checks.append(QCCheck(name="laenge_minimum", passed=length.verdict not in (LengthVerdict.TOO_SHORT, LengthVerdict.INVALID),
                              detail=length.message, value=a.duration_s))
        checks.append(QCCheck(name="laenge_maximum", passed=length.verdict != LengthVerdict.TOO_LONG, detail=length.message,
                              value=a.duration_s))
        checks.append(QCCheck(name="laenge_ideal", severity="warning", passed=length.verdict == LengthVerdict.IDEAL,
                              detail=length.message, value=a.duration_s))
        checks.append(QCCheck(name="format", passed=(a.width, a.height) == (s.video_width, s.video_height)
                              and a.video_codec == "h264" and a.audio_codec == "aac" and a.pix_fmt == "yuv420p",
                              detail=f"{a.width}x{a.height} {a.video_codec}/{a.audio_codec} {a.pix_fmt}"))
        checks.append(QCCheck(name="bildrate", passed=a.fps is not None and abs(a.fps - s.fps) < 0.01,
                              detail=f"{a.fps} fps", value=a.fps))
        lufs_ok = a.integrated_lufs is not None and LUFS_RANGE[0] <= a.integrated_lufs <= LUFS_RANGE[1]
        checks.append(QCCheck(name="lautheit", passed=lufs_ok, value=a.integrated_lufs,
                              detail=f"{a.integrated_lufs} LUFS (Ziel -14, erlaubt {LUFS_RANGE[0]}..{LUFS_RANGE[1]})"))
        checks.append(QCCheck(name="true_peak", severity="warning",
                              passed=a.true_peak_dbfs is not None and a.true_peak_dbfs <= -0.5,
                              detail=f"{a.true_peak_dbfs} dBFS", value=a.true_peak_dbfs))
        checks.append(QCCheck(name="keine_langen_pausen", passed=a.longest_silence_s <= MAX_SILENCE_S,
                              detail=f"längste Pause {a.longest_silence_s:.2f} s (max {MAX_SILENCE_S} s)",
                              value=a.longest_silence_s))
        checks.append(QCCheck(name="keine_standbilder", passed=a.longest_freeze_s <= MAX_FREEZE_S,
                              detail=f"längstes Standbild {a.longest_freeze_s:.2f} s (max {MAX_FREEZE_S} s)",
                              value=a.longest_freeze_s))
        checks.append(QCCheck(name="keine_schwarzbilder", passed=not a.blacks, detail=f"{len(a.blacks)} Abschnitte"))

        # Untertitel
        spoken = sum(len(sc.words) for sc in scenes)
        shown = sum(len(c.words) for c in cues)
        coverage = shown / spoken if spoken else 0.0
        ordered = all(c.start < c.end for c in cues) and all(x.end <= y.start + 1e-3 for x, y in zip(cues, cues[1:]))
        inside = all(c.end <= a.duration_s + 0.05 for c in cues)
        checks.append(QCCheck(name="untertitel_vollstaendig", passed=spoken > 0 and coverage >= 0.98,
                              detail=f"{shown}/{spoken} Wörter", value=round(coverage, 3)))
        checks.append(QCCheck(name="untertitel_synchron", passed=ordered and inside,
                              detail="geordnet, ohne Überlappung, innerhalb der Videodauer" if ordered and inside
                              else "Überlappung oder ausserhalb der Dauer"))
        checks.append(QCCheck(name="untertitel_kurz", severity="warning",
                              passed=all(len(c.text) <= 24 for c in cues), detail="max. 24 Zeichen je Einblendung"))
        # Hook
        hook = scenes[0] if scenes else None
        first_word = hook.words[0].start if hook and hook.words else 99.0
        hook_ok = bool(hook) and hook.role == "hook" and word_count(hook.text) <= HOOK_MAX_WORDS \
            and first_word <= HOOK_START_MAX_S and hook.duration_s <= HOOK_END_MAX_S
        checks.append(QCCheck(name="hook_sofort", passed=hook_ok,
                              detail=f"Hook beginnt bei {first_word:.2f} s, dauert {hook.duration_s if hook else 0:.2f} s"))
        # Sprechtempo (Orientierung 130–165 wpm)
        total_audio = sum(sc.duration_s for sc in scenes)
        wpm = script.word_count / total_audio * 60 if total_audio else 0
        checks.append(QCCheck(name="sprechtempo", severity="warning", passed=s.wpm_min <= wpm <= s.wpm_max * 1.1,
                              detail=f"{wpm:.0f} Wörter/min (Orientierung {s.wpm_min:.0f}–{s.wpm_max:.0f})", value=round(wpm, 1)))
        checks.append(QCCheck(name="quellen_verifiziert", passed=sources_verified and bool(script.sources),
                              detail=f"{len(script.sources)} Quelle(n)"))
        return QCReport(checks=checks)
