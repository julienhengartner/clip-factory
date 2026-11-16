"""Content-Strategie: Stilprofil, Themenkategorien, Ideenbildung und Themenauswahl.

Das Stilprofil ist zunächst eine ANNAHME (source=default_assumption), weil die Instagram-Inhalte ohne
autorisierten Zugriff nicht ausgewertet werden. Es lässt sich über data/style_profile.json überschreiben
(dann source=user) – siehe README.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

from brain.memory import Memory
from config import Settings
from core.text import keyword_set, keywords, similarity
from storage.models import Idea, ResearchItem, StyleProfile

DEFAULT_STYLE = StyleProfile(
    persona="Bürgermeister Bob erzählt in der Ich-Form, nahbar und augenzwinkernd",
    tone="freundlich, neugierig, leicht humorvoll, nie herablassend",
    humor="Situationskomik und überraschende Wendungen; kein Spott über Menschen, keine Witze über Tragödien",
    language="Hochdeutsch, kurze Sätze, Du-Ansprache, gut sprechbar",
    narrative="Hook -> Einordnung -> Geschichte mit Wendepunkt -> Erkenntnis -> Frage an die Community",
    topics=["kuriose Geschichte", "Erfindungen", "Gemeinde und Alltag", "Wissen", "Natur", "Gesellschaft"],
    audience="deutschsprachige TikTok-Nutzer, die Unterhaltung mit Wissen mögen",
    visual_style="kräftige Farben, grosse Schlagworte, ruhige Kamerafahrten, Wechsel alle 3–5 Sekunden",
    editing_style="harte Schnitte, Wort-für-Wort-Untertitel, keine Pausen",
    recurring_elements=["Marken-Pille 'BÜRGERMEISTER BOB'", "Abschlussfrage an die Community", "Folg-Bob-Abschluss"],
)

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "technik": ["erfind", "maschine", "patent", "technik", "computer", "motor", "rakete", "raumfahrt", "nasa",
                "fahrrad", "auto", "eisenbahn", "flugzeug", "telefon", "internet", "elektr"],
    "wissenschaft": ["forsch", "entdeck", "wissenschaft", "physik", "chemie", "astronom", "medizin", "nobelpreis",
                     "planet", "mond", "stern", "biolog"],
    "geschichte": ["jahrhundert", "kaiser", "könig", "gegründet", "gründung", "historisch", "mittelalter",
                   "revolution", "vertrag", "reich"],
    "politik": ["wahl", "regierung", "parlament", "gesetz", "bürgermeister", "gemeinde", "stadtrat", "abstimmung",
                "verfassung", "partei", "minister"],
    "kultur": ["film", "musik", "album", "roman", "theater", "kunst", "museum", "oper", "band", "maler"],
    "sport": ["fussball", "fußball", "olymp", "weltmeister", "meisterschaft", "turnier", "sieg", "rekord"],
    "natur": ["tier", "pflanze", "wald", "berg", "see", "fluss", "klima", "wetter", "vogel", "natur"],
}
SENSITIVE = ["krieg", "anschlag", "terror", "mord", "massaker", "völkermord", "holocaust", "attentat", "hinricht",
             "getötet", "tote", "toten", "opfer", "bombard", "absturz", "katastroph", "pogrom", "genozid",
             "schießerei", "schiesserei", "amoklauf", "erdbeben", "tsunami", "hungersnot", "deportation",
             "konzentrationslager", "explosion", "epidemie", "pandemie", "suizid", "selbstmord", "vergewaltig",
             "geisel", "invasion", "besetzung", "luftangriff", "verhaftet", "gefangen", "kapitulation", "schlacht",
             "selbstverbrenn", "starb", "verstorb", "ermordet", "hingerichtet", "verunglück", "unglück", "tödlich",
             "todesopfer", "brandkatastroph", "überschwemmung", "entführ", "missbrauch", "folter", "putsch",
             "nationalistisch", "rechtsextrem", "linksextrem", "neonazi", "extremist", "terrorist", "nationalsozialis",
             "vereinsverbot", "verfassungsfeind"]

ANGLES = {
    "technik": "Wie eine Erfindung unseren Alltag verändert hat",
    "wissenschaft": "Eine Entdeckung, die überrascht",
    "geschichte": "Was damals passiert ist – und was es mit heute zu tun hat",
    "politik": "Wie Entscheidungen das Zusammenleben prägen",
    "kultur": "Die Geschichte hinter einem Kulturmoment",
    "sport": "Ein Moment, über den man noch heute spricht",
    "natur": "Erstaunliches aus der Natur",
    "allgemein": "Eine Geschichte, die kaum jemand kennt",
}

NOVELTY_REJECT = 0.5   # ab dieser Ähnlichkeit zu einem früheren Video gilt ein Thema als Wiederholung


def categorize(text: str) -> str:
    low = text.lower()
    if any(w in low for w in SENSITIVE):
        return "sensibel"
    scores = {cat: sum(low.count(k) for k in kws) for cat, kws in CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "allgemein"


class Strategy:
    def __init__(self, settings: Settings, memory: Memory, rng: random.Random | None = None):
        self.s, self.memory = settings, memory
        self.rng = rng or random.Random()

    # --- Stilprofil ---------------------------------------------------------------
    @property
    def style_file(self) -> Path:
        return self.s.data_dir / "style_profile.json"

    def ensure_style_file(self) -> Path:
        """Legt data/style_profile.json aus den Beobachtungen an, falls noch nicht vorhanden (nie überschreiben)."""
        if not self.style_file.is_file():
            from brain.style_observations import STYLE_PROFILE
            self.style_file.parent.mkdir(parents=True, exist_ok=True)
            self.style_file.write_text(json.dumps(STYLE_PROFILE, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.style_file

    def style(self) -> StyleProfile:
        if self.s.content_mode == "bobstadt":
            self.ensure_style_file()
        if self.style_file.is_file():
            data = json.loads(self.style_file.read_text(encoding="utf-8"))
            if "annahmen" in data or "gesichert" in data:   # strukturiertes Profil (Beobachtung + Annahmen)
                fields = {k: v for k, v in data.get("annahmen", {}).items() if k in StyleProfile.model_fields}
                return StyleProfile(**{**DEFAULT_STYLE.model_dump(), **fields,
                                       "source": "observed+assumptions", "confirmed": bool(data.get("bestaetigt"))})
            return StyleProfile(**{**DEFAULT_STYLE.model_dump(), **data, "source": "user", "confirmed": True})
        stored = self.memory.get_insight("style", "profile")
        if stored:
            return StyleProfile(**stored)
        self.memory.set_insight("style", "profile", DEFAULT_STYLE.model_dump(), confidence=0.2)
        return DEFAULT_STYLE

    # --- Ideen --------------------------------------------------------------------
    def ideas_from_research(self, items: list[ResearchItem], origin: str = "research") -> list[Idea]:
        known = self.memory.idea_titles()
        produced = self.memory.produced_topics()
        new = []
        for item in items:
            if not item.verified or item.id is None or item.category == "sensibel":
                continue
            if any(similarity(item.title, t) >= 0.8 or item.title.lower() == t.lower() for t in known):
                continue
            idea = Idea(title=item.title, angle=ANGLES.get(item.category, ANGLES["allgemein"]),
                        category=item.category, research_ids=[item.id], origin=origin)
            idea.score = self.score(idea, item.summary, produced)
            if idea.score <= 0:
                continue
            idea.id = self.memory.add_idea(idea)
            known.append(idea.title)
            new.append(idea)
        return new

    def novelty(self, title: str, context: str = "", produced: list[str] | None = None) -> float:
        """1 = völlig neu, 0 = Wiederholung. Titel vollständig in früherem Thema enthalten -> Wiederholung."""
        produced = self.memory.produced_topics() if produced is None else produced
        if not produced:
            return 1.0
        title_kw = keyword_set(title)
        combined = f"{title} {context}"
        worst = 0.0
        for p in produced:
            p_kw = keyword_set(p)
            if title_kw and title_kw <= p_kw:
                return 0.0
            worst = max(worst, similarity(combined, p))
        return 1.0 - worst

    def score(self, idea: Idea, context: str = "", produced: list[str] | None = None) -> float:
        novelty = self.novelty(idea.title, " ".join(keywords(context, 3)), produced)
        if novelty < 1 - NOVELTY_REJECT:
            return 0.0
        cat = self.memory.get_insight("topic_category", idea.category) or {}
        learned = float(cat.get("mean", 1.0))
        n = int(cat.get("n", 0))
        exploration = 0.25 / math.sqrt(n + 1)
        bonus = 0.3 if idea.origin == "comment" else 0.0
        return round(learned * (0.5 + 0.5 * novelty) + exploration + bonus, 4)

    def rescore(self) -> None:
        produced = self.memory.produced_topics()
        for idea in self.memory.list_ideas("new"):
            items = self.memory.get_research(idea.research_ids)
            ctx = " ".join(i.summary for i in items)
            if categorize(f"{idea.title} {ctx}") == "sensibel":  # Filter wird laufend verbessert
                self.memory.update_idea(idea.id, status="rejected")
                continue
            new = self.score(idea, ctx, produced)
            self.memory.update_idea(idea.id, score=new, **({"status": "rejected"} if new <= 0 else {}))

    def choose_idea(self, exclude: set[int] | None = None) -> Idea | None:
        self.rescore()
        candidates = [i for i in self.memory.list_ideas("new") if not exclude or i.id not in exclude]
        if not candidates:
            return None
        # leichte Zufallskomponente gegen Einseitigkeit (Exploration)
        return max(candidates, key=lambda i: i.score * (0.9 + 0.2 * self.rng.random()))
