"""Deutsche Textwerkzeuge: Sätze, Wörter, Schlüsselwörter, Ähnlichkeit, Sprechdauer."""
from __future__ import annotations

import re
import unicodedata

STOPWORDS = set("""
aber alle allem allen aller alles als also am an ander andere anderen anderer anderes auch auf aus bei bin bis bist
da dabei damit dann das dass dein deine dem den denn der des dessen dich die dies diese diesem diesen dieser dieses
dir doch dort du durch ein eine einem einen einer eines einige er es etwas euch euer für gegen gewesen hab habe haben
hat hatte hatten hier hin hinter ich ihm ihn ihnen ihr ihre im in indem ins ist ja jede jedem jeden jeder jedes jetzt
kann kein keine können könnte machen man manche mehr mein meine mich mir mit muss musste nach nicht nichts noch nun nur
ob oder ohne sehr sein seine seit sich sie sind so solche soll sollte sondern sonst über um und uns unser unsere unter
viel vom von vor wann war waren warum was weg weil weiter welche welchem welchen welcher welches wenn wer werde werden
wie wieder will wir wird wirst wo wurde wurden zu zum zur zwar zwischen heute wurde worden sowie bzw etwa rund mal
schon immer ganz gibt geht wirklich einfach heute dass bob bürgermeister jahr jahre jahren ersten erste neue neuen
""".split())

_ABBREVIATIONS = ("z. B.", "z.B.", "u. a.", "u.a.", "d. h.", "d.h.", "bzw.", "ca.", "Dr.", "Prof.", "Nr.", "St.",
                  "etc.", "vgl.", "evtl.", "usw.", "Mio.", "Mrd.", "Jh.", "v. Chr.", "n. Chr.", "geb.", "gest.")
_PLACEHOLDER = "⁣"  # unsichtbares Trennzeichen als temporärer Ersatz für Punkte in Abkürzungen

_WORD_RE = re.compile(r"[0-9A-Za-zÄÖÜäöüßÀ-ÿ]+(?:[-'’][0-9A-Za-zÄÖÜäöüßÀ-ÿ]+)*")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_research_text(text: str) -> str:
    """Entfernt Klammer-Einschübe (Aussprache, Lebensdaten), Fussnoten und HTML-Reste."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\[\d+\]", "", text)
    for _ in range(2):  # verschachtelte Klammern
        text = re.sub(r"\s*\([^()]*\)", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    return normalize_space(text)


def split_sentences(text: str) -> list[str]:
    text = normalize_space(text)
    if not text:
        return []
    protected = text
    for abbr in _ABBREVIATIONS:
        protected = protected.replace(abbr, abbr.replace(".", _PLACEHOLDER))
    # Ordinalzahlen / Datumsangaben wie "12. Juni" nicht trennen
    protected = re.sub(r"(\d)\.(?=\s+[a-zäöüA-ZÄÖÜ])", lambda m: m.group(1) + _PLACEHOLDER, protected)
    parts = re.split(r"(?<=[.!?…])\s+(?=[\"„»A-ZÄÖÜ0-9])", protected)
    return [p.replace(_PLACEHOLDER, ".").strip() for p in parts if p.strip()]


def words(text: str) -> list[str]:
    return _WORD_RE.findall(text or "")


def word_count(text: str) -> int:
    return len(words(text))


def keywords(text: str, n: int = 5) -> list[str]:
    counts: dict[str, int] = {}
    original: dict[str, str] = {}
    for w in words(text):
        lw = w.lower()
        if len(lw) < 4 or lw in STOPWORDS or lw.isdigit():
            continue
        counts[lw] = counts.get(lw, 0) + 1 + (1 if w[0].isupper() else 0)  # Nomen leicht bevorzugen
        original.setdefault(lw, w)
    ranked = sorted(counts, key=lambda k: (-counts[k], -len(k)))
    return [original[k] for k in ranked[:n]]


def keyword_set(text: str) -> set[str]:
    return {w.lower() for w in words(text) if len(w) >= 4 and w.lower() not in STOPWORDS}


def similarity(a: str, b: str) -> float:
    """Jaccard-Ähnlichkeit der Schlüsselwortmengen (0..1)."""
    sa, sb = keyword_set(a), keyword_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def estimate_duration_s(text: str, wpm: float) -> float:
    return word_count(text) / wpm * 60.0


def words_for_duration(seconds: float, wpm: float) -> int:
    return int(round(seconds * wpm / 60.0))


def slug(text: str, max_len: int = 40) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t[:max_len] or "video"


def first_number(text: str) -> str | None:
    m = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", text) or re.search(r"\b\d+(?:[.,]\d+)?\b", text)
    return m.group(0) if m else None
