"""Image Generation Agent: erzeugt die Bilder je Shot.

- Bobstadt-Szenen (Episoden): isometrische Stadtansicht aus dem echten Stadtzustand, mit Bau-Animation
  und Overlays (Preis, Finanzierung, Abstimmung, Meilenstein) – kostenlos, lokal.
- Wissensteil und sonstige Szenen: Motion-Graphics-Karten (procedural, kostenlos).
- openai (kostenpflichtig, nur nach Freigabe): ein KI-Bild pro Szene, mit Cache gegen Doppelkosten.
"""
from __future__ import annotations

from pathlib import Path

from agents.base import Agent, AgentContext
from storage.models import Scene
from video_engine.isometric import render_build_frames, render_city
from video_engine.visuals import cover_resize, oversized, render_background

CITY_STYLES = {"city", "build", "cost", "funding", "vote", "vote_result", "milestone"}
# Episoden: diese Rollen zeigen ebenfalls die Stadt (mit passendem Overlay)
CITY_ROLES = {"hook": "keyword", "intro": "city", "plot": None, "takeaway": "city"}


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

    def _city_overlay(self, sc: Scene) -> str | None:
        if sc.style in CITY_STYLES:
            return {"city": None, "build": None, "vote_result": "keyword"}.get(sc.style, sc.style)
        return CITY_ROLES.get(sc.role)

    def create(self, scenes: list[Scene], out_dir: Path, title: str, city: dict | None = None) -> list[Scene]:
        out_dir.mkdir(parents=True, exist_ok=True)
        fonts = dict(display_font=self.s.font_path(self.s.display_font), bold_font=self.s.font_path(self.s.bold_font))
        W, H = oversized(self.s.video_width, self.s.video_height)
        result = []
        build_at = next((s.index for s in scenes if s.style == "build"), None)
        for sc in scenes:
            shots = []
            use_city = city is not None and (sc.style in CITY_STYLES or sc.role in CITY_ROLES)
            ai_image = None
            if self.provider == "openai" and not use_city:
                raw = self._openai_service().generate_image(sc.image_prompt, out_dir / f"ai_{sc.index:02d}_raw.png")
                ai_image = cover_resize(raw, out_dir / f"ai_{sc.index:02d}.png", self.s.video_width, self.s.video_height)
            for k, shot in enumerate(sc.shots):
                if use_city:
                    # neues Gebäude erst ab der Bauszene (vorher nur als Preisschild/Plan sichtbar)
                    show = sc.style in ("build", "cost") or (build_at is not None and sc.index > build_at)
                    highlight = city.get("highlight") if show else None
                    if sc.style == "build" and k == 0 and highlight:
                        frames = max(1, round(shot.duration * self.s.fps))
                        fdir = render_build_frames(out_dir / f"build_{sc.index:02d}", self.s.video_width,
                                                   self.s.video_height, city, highlight, frames,
                                                   data=sc.data, palette=sc.index, **fonts)
                        shots.append(shot.model_copy(update={"frames_dir": str(fdir)}))
                        continue
                    path = out_dir / f"city_{sc.index:02d}_{k}.png"
                    render_city(path, W, H, city, highlight=highlight, overlay=self._city_overlay(sc),
                                data={**sc.data, "keyword": sc.data.get("keyword") or (title if sc.role == "hook" else
                                                                                         sc.keyword)},
                                palette=sc.index, safe_top=0.2, margin=0.2, title=title, **fonts)
                elif ai_image:
                    path = ai_image
                else:
                    path = render_background(
                        out_dir / f"img_{sc.index:02d}_{k}.png", self.s.video_width, self.s.video_height,
                        style=sc.style if k == 0 else ("keyword" if sc.style in ("hook", "title", "cta") else sc.style),
                        keyword=sc.keyword, number=sc.number, title=title, palette=(sc.palette + k) % 6,
                        variant=k, **fonts)
                shots.append(shot.model_copy(update={"image_path": str(path)}))
            result.append(sc.model_copy(update={"shots": shots}))
        return result
