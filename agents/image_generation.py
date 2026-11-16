"""Image Generation Agent: erzeugt die Bilder je Shot.

- procedural (Standard, kostenlos): Motion-Graphics-Karten mit Schlagworten, Variante pro Shot.
- openai (kostenpflichtig): ein KI-Bild pro Szene über die OpenAI-API (mit Cache gegen Doppelkosten);
  Shots derselben Szene nutzen es mit unterschiedlicher Kamerabewegung.
"""
from __future__ import annotations

from pathlib import Path

from agents.base import Agent, AgentContext
from storage.models import Scene
from video_engine.visuals import cover_resize, render_background


class ImageGenerationAgent(Agent):
    name = "image_generation"

    def __init__(self, ctx: AgentContext, openai_service=None):
        super().__init__(ctx)
        self._openai = openai_service

    @property
    def provider(self) -> str:
        return self.s.image_provider

    def _openai_service(self):
        if self._openai is None:
            from integrations.openai_api import OpenAIService
            self._openai = OpenAIService(self.s, self.ctx.budget)
        return self._openai

    def create(self, scenes: list[Scene], out_dir: Path, title: str) -> list[Scene]:
        out_dir.mkdir(parents=True, exist_ok=True)
        result = []
        for sc in scenes:
            shots = []
            ai_image = None
            if self.provider == "openai":
                raw = self._openai_service().generate_image(sc.image_prompt, out_dir / f"ai_{sc.index:02d}_raw.png")
                ai_image = cover_resize(raw, out_dir / f"ai_{sc.index:02d}.png", self.s.video_width, self.s.video_height)
            for k, shot in enumerate(sc.shots):
                if ai_image:
                    path = ai_image
                else:
                    path = render_background(
                        out_dir / f"img_{sc.index:02d}_{k}.png", self.s.video_width, self.s.video_height,
                        style=sc.style if k == 0 else ("keyword" if sc.style in ("hook", "title", "cta") else sc.style),
                        keyword=sc.keyword, number=sc.number, title=title, palette=(sc.palette + k) % 6,
                        variant=k, display_font=self.s.font_path(self.s.display_font),
                        bold_font=self.s.font_path(self.s.bold_font))
                shots.append(shot.model_copy(update={"image_path": str(path)}))
            result.append(sc.model_copy(update={"shots": shots}))
        return result
