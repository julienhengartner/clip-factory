"""Endschnitt: Shots -> Videospur, Sprachspur (+ optionale lizenzierte Musik), Untertitel einbrennen -> MP4."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from config import Settings
from storage.models import Scene
from video_engine.ffmpeg import escape_filter_value, probe_duration, run_ffmpeg
from video_engine.scenes import render_shot


class VideoRenderer:
    def __init__(self, settings: Settings):
        self.s = settings

    def render_video_track(self, scenes: list[Scene], out_path: Path, workdir: Path) -> Path:
        clips = []
        for sc in scenes:
            for k, shot in enumerate(sc.shots):
                if not shot.image_path and not shot.frames_dir:
                    raise ValueError(f"Szene {sc.index}, Shot {k}: kein Bild")
                clips.append(render_shot(Path(shot.image_path or "."), shot, workdir / f"s{sc.index:02d}_{k}.mp4", self.s))
        lst = workdir / "clips.txt"
        lst.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out_path)], self.s.ffmpeg_bin)
        return out_path

    def render(self, scenes: list[Scene], voice_wav: Path, ass_path: Path | None, out_path: Path,
               music: Path | None = None) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        total = probe_duration(voice_wav, self.s.ffprobe_bin)
        workdir = Path(tempfile.mkdtemp(prefix="bbob_render_"))
        try:
            video = self.render_video_track(scenes, workdir / "video.mp4", workdir)
            inputs = ["-i", str(video), "-i", str(voice_wav)]
            vf = "[0:v]null"
            if ass_path:
                vf = (f"[0:v]subtitles=filename='{escape_filter_value(ass_path)}'"
                      f":fontsdir='{escape_filter_value(self.s.fonts_dir)}'")
            voice = "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100,aformat=channel_layouts=stereo"
            if music:
                inputs += ["-stream_loop", "-1", "-i", str(music)]
                fade_out = max(0.0, total - 2.0)
                graph = (f"{vf}[v];{voice}[vo];[2:a]aresample=44100,aformat=channel_layouts=stereo,volume=0.10,"
                         f"afade=t=in:d=1.5,afade=t=out:st={fade_out:.2f}:d=2[mu];"
                         f"[vo][mu]amix=inputs=2:duration=first:normalize=0[a]")
            else:
                graph = f"{vf}[v];{voice}[a]"
            run_ffmpeg([*inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-r", str(self.s.fps), "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
                        "-t", f"{total:.3f}", "-movflags", "+faststart", str(out_path)], self.s.ffmpeg_bin)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        return out_path

    def thumbnail(self, video: Path, out_path: Path, at_s: float = 1.0) -> Path:
        run_ffmpeg(["-ss", f"{at_s:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "3",
                    str(out_path)], self.s.ffmpeg_bin)
        return Path(out_path)
