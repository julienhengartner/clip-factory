"""Comment Analysis Agent: ordnet Kommentare ein (Frage, Lob, Kritik, Themenvorschlag, Spam, Sonstiges)
und leitet daraus Themenwünsche der Community ab. Regelbasiert, lokal, kostenlos."""
from __future__ import annotations

import re
from collections import Counter

from agents.base import Agent
from core.text import keywords

QUESTION_WORDS = ("wer", "wie", "was", "wo", "wann", "warum", "wieso", "weshalb", "welche", "welcher", "welches",
                  "kannst du", "könntest du", "gibt es", "stimmt es")
SUGGESTION = ("mach mal", "mach bitte", "mach doch", "video über", "video zu", "erzähl", "erklär", "thema",
              "bitte mehr", "mehr über", "teil 2", "nächstes mal")
PRAISE = ("super", "toll", "genial", "stark", "cool", "klasse", "danke", "mega", "lustig", "witzig", "liebe",
          "geil", "beste", "großartig", "grossartig", "gefällt", "spannend", "interessant", "❤", "😍", "👏", "😂", "🔥", "👍")
CRITICISM = ("falsch", "stimmt nicht", "schlecht", "langweilig", "nervig", "fehler", "quatsch", "unsinn", "blödsinn",
             "schlimm", "peinlich", "enttäusch", "ki-müll", "fake", "👎", "zu lang", "zu schnell", "roboter")
SPAM = (r"https?://", r"www\.", r"follow\s*(me|back)", r"folg(t)?\s*mir", r"check\s*(out\s*)?my", r"\bdm\b",
        r"krypto|crypto|bitcoin|forex|invest", r"gewinnspiel|gratis|free followers", r"onlyfans|telegram")


def classify(text: str) -> tuple[str, float]:
    """Gibt (Kategorie, Stimmung -1..1) zurück."""
    low = text.lower().strip()
    if not low:
        return "sonstiges", 0.0
    if any(re.search(p, low) for p in SPAM) or re.fullmatch(r"(.)\1{6,}", low.replace(" ", "")):
        return "spam", 0.0
    pos = sum(low.count(w) for w in PRAISE)
    neg = sum(low.count(w) for w in CRITICISM)
    sentiment = 0.0 if pos == neg == 0 else round((pos - neg) / (pos + neg), 2)
    if any(s in low for s in SUGGESTION):
        return "themenvorschlag", sentiment
    if "?" in low or low.startswith(QUESTION_WORDS):
        return "frage", sentiment
    if neg > pos:
        return "kritik", sentiment
    if pos > 0:
        return "lob", sentiment
    return "sonstiges", sentiment


class CommentAnalysisAgent(Agent):
    name = "comment_analysis"

    def analyze_pending(self) -> dict[str, int]:
        counts: Counter = Counter()
        for c in self.memory.unanalyzed_comments():
            cat, sentiment = classify(c["text"])
            kws = [] if cat == "spam" else keywords(c["text"], 3)
            self.memory.set_comment_analysis(c["id"], cat, sentiment, kws)
            counts[cat] += 1
        if counts:
            self.event("info", "Kommentare analysiert: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
        return dict(counts)

    def audience_requests(self, limit: int = 5) -> list[str]:
        """Häufigste Schlüsselwörter aus Fragen und Themenvorschlägen -> mögliche neue Themen."""
        import json
        counter: Counter = Counter()
        for cat in ("themenvorschlag", "frage"):
            for c in self.memory.comments(cat):
                for kw in json.loads(c["keywords"] or "[]"):
                    counter[kw] += 2 if cat == "themenvorschlag" else 1
        top = [k for k, _ in counter.most_common(limit)]
        self.memory.set_insight("audience", "requests", top, confidence=min(1.0, sum(counter.values()) / 50))
        return top

    def summary(self) -> dict:
        rows = self.memory.comments(limit=1000)
        cats = Counter(r["category"] for r in rows if r["category"])
        sentiments = [r["sentiment"] for r in rows if r["sentiment"] is not None and r["category"] != "spam"]
        result = {"total": len(rows), "categories": dict(cats),
                  "avg_sentiment": round(sum(sentiments) / len(sentiments), 3) if sentiments else None}
        self.memory.set_insight("audience", "comment_summary", result)
        return result
