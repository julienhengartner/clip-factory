"""Hook Agent: entwickelt mehrere Einstiege und wählt den besten anhand gelernter Muster-Leistung.

Regeln: Der Hook muss in höchstens ~3 Sekunden gesprochen sein. Die erlaubte Wortzahl wird aus der
GEMESSENEN Sprechrate abgeleitet (z. B. 140 wpm -> 7 Wörter). Ein Satz, konkret, neugierig machend.
Auswahl = gelernter Mittelwert des Musters + Explorationsbonus für selten getestete Muster.
"""
from __future__ import annotations

import math
import random

from agents.base import Agent
from core.text import first_number, keywords, word_count, words
from storage.models import HookCandidate, Idea

HOOK_SECONDS = 3.0

# Vorlagen bewusst ohne Artikel/Fallbeugung vor {kw} – sonst entstehen Fehler wie "hinter Telefons".
PATTERNS: dict[str, list[str]] = {
    "wusstest_du": ["{kw} – das wusstest du bestimmt nicht.", "{kw}: Wusstest du das?"],
    "frage": ["Stichwort {kw}: Was weisst du darüber?", "{kw}. Was steckt wirklich dahinter?"],
    "zahl": ["{num} – und plötzlich war alles anders.", "{num}: ein Jahr, das niemand vergisst."],
    "kontrast": ["{kw}? Kaum jemand kennt diese Geschichte.", "{kw} – nicht, was du denkst."],
    "geheimnis": ["{kw}: Diese Geschichte glaubt mir keiner.", "Thema {kw}. Und es wird kurios."],
    "bob": ["Bob hier – und heute wird es kurios.", "Das müsst ihr hören, sagt Bob."],
}


def max_hook_words(wpm: float) -> int:
    return max(5, min(10, int(HOOK_SECONDS * wpm / 60)))


def hook_keyword(idea: Idea, context: str) -> str:
    """Kurzes, prägnantes Schlagwort: kurzer Titel oder das Titelwort, das im Material am häufigsten vorkommt."""
    title = idea.title.strip()
    if word_count(title) <= 4 and len(title) <= 30:
        return title
    ctx_low = context.lower()
    candidates = [w for w in words(title) if len(w) >= 4]
    if candidates:
        return max(candidates, key=lambda w: (ctx_low.count(w.lower()), len(w)))
    kws = keywords(f"{title} {context}", 1)
    return kws[0] if kws else title


class HookAgent(Agent):
    name = "hook"

    def candidates(self, idea: Idea, context: str, wpm: float = 150.0) -> list[HookCandidate]:
        kw = hook_keyword(idea, context)
        num = first_number(context)
        year = num if num and len(num) == 4 else None
        limit = max_hook_words(wpm)
        out = []
        for pattern, templates in PATTERNS.items():
            if pattern == "zahl" and not year:
                continue
            for t in templates:
                text = t.format(kw=kw, num=year or "")
                if word_count(text) <= limit:
                    out.append(HookCandidate(text=text, pattern=pattern))
        if not out:  # Schlagwort zu lang -> kürzestes Muster mit verkürztem Schlagwort
            out.append(HookCandidate(text=f"Bob hier – und heute wird es kurios.", pattern="bob"))
        return out

    def choose(self, idea: Idea, context: str, wpm: float = 150.0,
               rng: random.Random | None = None) -> tuple[HookCandidate, list[HookCandidate]]:
        rng = rng or random.Random(idea.title)
        learned = self.memory.insights("hook_pattern")
        cands = self.candidates(idea, context, wpm)
        for c in cands:
            stats = learned.get(c.pattern, {})
            mean, n = float(stats.get("mean", 1.0)), int(stats.get("n", 0))
            c.score = round(mean + 0.3 / math.sqrt(n + 1) + rng.random() * 0.05, 4)
        cands.sort(key=lambda c: c.score, reverse=True)
        return cands[0], cands
