"""Video Director Agent: plant Szenen, Dramaturgie und visuelle Umsetzung.

- Hook steht allein in Szene 0 (startet sofort, < 3 s).
- Szenen umfassen 1–2 Sätze (max. ~24 Wörter), damit das Bild oft wechselt.
- Bildstil folgt dem Inhalt: Jahreszahl -> grosse Zahl, Frage -> Fragezeichen, Wendepunkt -> Zitat-Karte.
- Lange Szenen werden später zusätzlich in Shots ≤ max_shot_s mit wechselnder Kamerabewegung geteilt.
"""
from __future__ import annotations

from agents.base import Agent
from core.text import first_number, keywords, split_sentences, word_count
from storage.models import Scene, Script, StyleProfile

MAX_SCENE_WORDS = 24


class VideoDirectorAgent(Agent):
    name = "video_director"

    def plan(self, script: Script, style: StyleProfile) -> list[Scene]:
        groups: list[tuple[str, str]] = []
        for seg in script.segments:
            if seg.role in ("hook", "cta", "turn", "intro", "takeaway"):
                groups.append((seg.role, seg.text))
                continue
            buf = ""
            for sent in split_sentences(seg.text) or [seg.text]:
                if buf and word_count(buf) + word_count(sent) > MAX_SCENE_WORDS:
                    groups.append((seg.role, buf))
                    buf = sent
                else:
                    buf = f"{buf} {sent}".strip()
            if buf:
                groups.append((seg.role, buf))
        # aufeinanderfolgende kurze Story-Gruppen zusammenführen
        merged: list[tuple[str, str]] = []
        for role, text in groups:
            if merged and role == "story" and merged[-1][0] == "story" and \
                    word_count(merged[-1][1]) + word_count(text) <= MAX_SCENE_WORDS:
                merged[-1] = (role, f"{merged[-1][1]} {text}")
            else:
                merged.append((role, text))

        scenes, prev_kw = [], ""
        title_kw = (keywords(script.title, 1) or [script.title])[0]
        for i, (role, text) in enumerate(merged):
            number = first_number(text)
            year = number if number and len(number) == 4 else None
            if role == "hook":
                style_name = "hook"
            elif role == "intro":
                style_name = "title"
            elif role == "cta":
                style_name = "cta"
            elif role == "turn":
                style_name = "quote"
            elif year:
                style_name = "number"
            elif text.rstrip().endswith("?"):
                style_name = "question"
            else:
                style_name = "keyword"
            kws = [k for k in keywords(text, 3) if k.lower() != prev_kw.lower()]
            kw = title_kw if role in ("hook", "intro", "turn") else (kws[0] if kws else title_kw)
            prev_kw = kw
            prompt = (f"Hochformat-Illustration 9:16 für ein TikTok-Video. Stil: {style.visual_style}. "
                      f"Motiv passend zu: {text} Ohne Schrift, ohne Logos, keine realen erkennbaren Personen.")
            scenes.append(Scene(index=i, role=role, text=text, style=style_name, keyword=kw, number=year,
                                palette=i % 6, image_prompt=prompt))
        return scenes
