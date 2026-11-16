"""Bobbington episode production (end to end, free and local).

    python -m bobbington.production episodes/pilot_mayor_bans_mondays.json [--quality draft|final]

Steps: script -> real voices (Piper) -> timeline with length fitting -> Blender render (one pass)
-> audio mix (dialogue, self-made SFX/music) -> English subtitles -> mux (H.264/AAC, 1080x1920)
-> quality control (ffprobe duration, format, loudness, freezes, black frames, subtitles, hook)
-> archive in the video library (status 'ready' only if QC passed).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from bobbington.episode import Episode, load_episode
from bobbington.timeline import Timeline, TimelineBuilder, mix_audio, write_timeline
from bobbington.voices import VOICE_CREDITS, VoiceBank
from bobbington.bible import CAST, SERIES
from config import Settings, get_settings
from storage.models import QCCheck, QCReport
from video_engine.duration import LengthVerdict, evaluate_length
from video_engine.ffmpeg import escape_filter_value, run_ffmpeg
from video_engine.quality_check import analyze

ROOT = Path(__file__).resolve().parent.parent


def ass_subtitles(tl: Timeline, path: Path, width: int = 1080, height: int = 1920) -> Path:
    size = round(height * 0.04)

    def ts(t: float) -> str:
        cs = int(round(t * 100))
        return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\n"
            "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
            "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            # cream text (#F3E9D2), ink outline – British palette
            f"Style: Sub,Arial,{size},&H00D2E9F3,&H0027A2C9,&H001F1B1B,&H64000000,-1,0,0,0,100,100,0,0,1,"
            f"{max(2, size // 12)},{max(1, size // 24)},2,{width // 12},{width // 12},{round(height * 0.2)},1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = [f"Dialogue: 0,{ts(c.start)},{ts(c.end)},Sub,,0,0,0,,{c.text.replace('{', '(').replace('}', ')')}"
             for c in tl.subtitles]
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def srt_subtitles(tl: Timeline, path: Path) -> Path:
    def ts(t: float) -> str:
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    path.write_text("\n".join(f"{i}\n{ts(c.start)} --> {ts(c.end)}\n{c.text}\n" for i, c in enumerate(tl.subtitles, 1)),
                    encoding="utf-8")
    return path


def credits_text(ep: Episode) -> str:
    models = sorted({CAST[l.speaker]["voice"]["model"] for s in ep.shots for l in s.lines})
    return "\n".join([f"{SERIES['title']} – {ep.title}", "Original series. All music and sound effects generated "
                      "in-house.", "Voices (synthetic, Piper TTS):"] + [f"  {VOICE_CREDITS[m]}" for m in models])


def quality_control(video: Path, tl: Timeline, settings: Settings) -> QCReport:
    a = analyze(video, settings)
    length = evaluate_length(a.duration_s, settings)
    first_speech = tl.shots[0].lines[0].speech_start if tl.shots and tl.shots[0].lines else 99
    hook_end = tl.shots[0].lines[0].speech_end if tl.shots and tl.shots[0].lines else 99
    covered = sum(len(c.text.split()) for c in tl.subtitles)
    spoken = sum(len(l.text.split()) for s in tl.shots for l in s.lines)
    checks = [
        QCCheck(name="length_minimum", passed=length.verdict not in (LengthVerdict.TOO_SHORT, LengthVerdict.INVALID),
                detail=length.message, value=a.duration_s),
        QCCheck(name="length_maximum", passed=length.verdict != LengthVerdict.TOO_LONG, detail=length.message),
        QCCheck(name="length_ideal", severity="warning", passed=length.verdict == LengthVerdict.IDEAL, detail=length.message),
        QCCheck(name="format", passed=(a.width, a.height, a.video_codec, a.audio_codec, a.pix_fmt) ==
                (1080, 1920, "h264", "aac", "yuv420p"), detail=f"{a.width}x{a.height} {a.video_codec}/{a.audio_codec} {a.pix_fmt}"),
        QCCheck(name="frame_rate", passed=a.fps is not None and abs(a.fps - tl.fps) < 0.01, detail=f"{a.fps} fps"),
        QCCheck(name="loudness", passed=a.integrated_lufs is not None and -18 <= a.integrated_lufs <= -10,
                detail=f"{a.integrated_lufs} LUFS"),
        QCCheck(name="no_long_silence", passed=a.longest_silence_s <= 1.5, detail=f"longest {a.longest_silence_s:.2f}s"),
        QCCheck(name="no_frozen_frames", passed=a.longest_freeze_s <= 2.5, detail=f"longest {a.longest_freeze_s:.2f}s"),
        QCCheck(name="no_black_frames", passed=not a.blacks, detail=f"{len(a.blacks)} segments"),
        QCCheck(name="hook_in_3_seconds", passed=first_speech <= 1.0 and hook_end <= 3.0,
                detail=f"hook spoken {first_speech:.2f}–{hook_end:.2f}s"),
        QCCheck(name="subtitles_complete", passed=covered == spoken, detail=f"{covered}/{spoken} words"),
    ]
    return QCReport(checks=checks)


class EpisodeProducer:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.s.ensure_dirs()
        self.voices = VoiceBank(self.s.piper_voices_dir, self.s.cache_dir / "tts")

    def _render_range(self, timeline_json: Path, out: Path, quality: str, first: int, last: int) -> Path:
        cmd = [str(self.s.blender_bin), "-b", "--factory-startup", "-P", str(ROOT / "blender" / "render_episode.py"),
               "--", str(timeline_json), str(out), quality, str(first), str(last)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        if proc.returncode != 0 or not out.is_file():
            tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-25:])
            raise RuntimeError(f"Blender render failed (frames {first}-{last}):\n{tail}")
        return out

    @staticmethod
    def _complete(path: Path, frames: int) -> bool:
        """A chunk counts as done only if ffprobe reads it with the expected frame count (no half files)."""
        if not path.is_file():
            return False
        proc = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                               "stream=nb_read_packets", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
        return proc.returncode == 0 and proc.stdout.strip().isdigit() and int(proc.stdout.strip()) == frames

    def render(self, timeline_json: Path, out: Path, quality: str, chunk_frames: int = 300) -> Path:
        """Renders in chunks (separate Blender runs) and resumes after an interruption: finished chunks are kept."""
        tl = json.loads(Path(timeline_json).read_text(encoding="utf-8"))
        total = tl["total_frames"]
        chunk_dir = out.parent / f"{out.stem}_chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        parts = []
        for i, first in enumerate(range(0, total, chunk_frames)):
            last = min(total, first + chunk_frames) - 1
            part = chunk_dir / f"chunk_{i:02d}_{first:05d}-{last:05d}.mp4"
            if not self._complete(part, last - first + 1):
                part.unlink(missing_ok=True)
                self._render_range(timeline_json, part, quality, first, last)
            parts.append(part)
        lst = chunk_dir / "list.txt"
        lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], self.s.ffmpeg_bin)
        return out

    def produce(self, episode_path: Path, quality: str = "final", work_dir: Path | None = None,
                reuse_render: Path | None = None) -> dict:
        ep = load_episode(episode_path)
        work = work_dir or (self.s.data_dir / "work" / ep.id)
        work.mkdir(parents=True, exist_ok=True)
        builder = TimelineBuilder(self.voices, fps=self.s.animation_fps)
        ep_final, tl = builder.fit(ep, self.s.min_duration_s, self.s.ideal_max_duration_s, self.s.hard_max_duration_s)
        tl_path = write_timeline(tl, work / "timeline.json")
        mix = mix_audio(ep_final, tl, work / "mix.wav")
        raw = reuse_render or self.render(tl_path, work / f"render_{quality}.mp4", quality)
        ass = ass_subtitles(tl, work / "subtitles.ass")

        out_dir = self.s.videos_dir / f"bobbington-{ep.id}-{quality}"
        out_dir.mkdir(parents=True, exist_ok=True)
        final = out_dir / "video.mp4"
        vf = (f"scale=1080:1920:flags=lanczos,subtitles=filename='{escape_filter_value(ass)}'"
              f":fontsdir='{escape_filter_value(self.s.fonts_dir)}',format=yuv420p")
        run_ffmpeg(["-i", str(raw), "-i", str(mix), "-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100,aformat=channel_layouts=stereo",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", str(self.s.animation_fps),
                    "-c:a", "aac", "-b:a", "192k", "-t", f"{tl.duration:.3f}", "-movflags", "+faststart", str(final)],
                   self.s.ffmpeg_bin)
        run_ffmpeg(["-ss", "6", "-i", str(final), "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "3",
                    str(out_dir / "thumbnail.jpg")], self.s.ffmpeg_bin)
        report = quality_control(final, tl, self.s)
        srt_subtitles(tl, out_dir / "subtitles.srt")
        shutil.copy(tl_path, out_dir / "timeline.json")
        (out_dir / "episode.json").write_text(ep_final.model_dump_json(indent=2), encoding="utf-8")
        (out_dir / "credits.txt").write_text(credits_text(ep_final), encoding="utf-8")
        (out_dir / "qc.json").write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")
        return {"episode": ep_final, "timeline": tl, "video": final, "thumbnail": out_dir / "thumbnail.jpg",
                "qc": report, "quality": quality, "out_dir": out_dir}

    def register(self, result: dict, memory) -> dict:
        """Adds the episode to the video library (status 'ready' only if QC passed)."""
        from storage.models import VideoStatus
        ep: Episode = result["episode"]
        report: QCReport = result["qc"]
        draft = result["quality"] != "final"
        v = memory.create_video(f"{ep.title}" + (" (draft render)" if draft else ""), None, "bobbington")
        script = {"segments": [{"role": "dialogue", "text": f"{CAST[l.speaker]['name']}: {l.text}"}
                               for s in ep.shots for l in s.lines], "sources": [], "provider": "bobbington-script"}
        return memory.update_video(
            v["id"], status=VideoStatus.READY if report.passed and not draft else VideoStatus.QC_FAILED,
            title=ep.title, hook=ep.shots[0].lines[0].text if ep.shots[0].lines else ep.title,
            video_path=str(result["video"]), thumbnail_path=str(result["thumbnail"]),
            duration_s=report.get("length_minimum").value, words=ep.word_count,
            script_json=script, episode_json={"bobbington": ep.model_dump()},
            qc_json={"passed": report.passed, "checks": [c.model_dump() for c in report.checks]},
            voice_provider="piper", image_provider="blender", script_provider="authored",
            error=None if report.passed and not draft else
            ("Draft render – produce in final quality before approval" if draft else
             "; ".join(c.detail for c in report.errors)))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Produce a Bobbington episode")
    p.add_argument("episode", type=Path)
    p.add_argument("--quality", choices=["draft", "final"], default="final")
    p.add_argument("--reuse-render", type=Path, help="skip Blender and use an existing render of this timeline")
    p.add_argument("--no-register", action="store_true")
    a = p.parse_args(argv)
    producer = EpisodeProducer()
    result = producer.produce(a.episode, a.quality, reuse_render=a.reuse_render)
    tl, report = result["timeline"], result["qc"]
    print(f"{result['episode'].title}: {tl.duration:.2f}s, {tl.total_frames} frames, adjustments={tl.adjustments}")
    for c in report.checks:
        print(f"  {'OK ' if c.passed else 'XX '} {c.severity:7} {c.name}: {c.detail}")
    print(f"QC {'PASSED' if report.passed else 'FAILED'} -> {result['video']}")
    if not a.no_register:
        from brain.memory import Memory
        from storage.database import Database
        v = producer.register(result, Memory(Database(producer.s.db_path)))
        print(f"library: {v['id']} status={v['status']}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
