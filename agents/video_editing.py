"""Video Editing Agent: schneidet Szenen, legt Sprache (und optional lizenzierte Musik) an und rendert 9:16-MP4."""
from __future__ import annotations

from pathlib import Path

from agents.base import Agent
from storage.models import Scene
from video_engine.audio import concat_wavs, pick_music
from video_engine.renderer import VideoRenderer
from video_engine.scenes import plan_shots


class VideoEditingAgent(Agent):
    name = "video_editing"

    def cut(self, scenes: list[Scene]) -> list[Scene]:
        return plan_shots(scenes, self.s.fps, self.s.max_shot_s)

    def assemble(self, scenes: list[Scene], ass_path: Path, out_dir: Path, seed: str) -> tuple[Path, Path, Path | None]:
        voice = out_dir / "voice.wav"
        concat_wavs([Path(sc.audio_path) for sc in scenes if sc.audio_path], voice, self.s)
        music = pick_music(self.s, seed)
        renderer = VideoRenderer(self.s)
        final = renderer.render(scenes, voice, ass_path, out_dir / "video.mp4", music)
        thumb = renderer.thumbnail(final, out_dir / "thumbnail.jpg", at_s=1.0)
        return final, thumb, music
