"""Research Agent: findet Themen und prüft Quellen.

Quellen (kostenlos, offiziell): Wikipedia-API (Suche, Artikel, "Was geschah am …") und konfigurierte
RSS-Feeds. Ein Eintrag gilt als VERIFIZIERT, wenn
  1. die Domain auf der Vertrauensliste steht,
  2. der Inhalt über die offizielle Schnittstelle bzw. die Original-URL tatsächlich abrufbar war und
  3. genügend Text vorhanden ist.
Nur verifizierte Einträge dürfen in Skripte einfliessen.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from agents.base import Agent, AgentContext
from brain.strategy import categorize
from core.errors import ExternalApiError
from core.text import split_sentences, word_count
from integrations.http import request
from integrations.rss import fetch_feed
from integrations.wikipedia import WikipediaClient
from storage.models import ResearchItem

MIN_WORDS_VERIFIED = 25
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]


def most_specific_page(event_text: str, pages: list[dict]) -> dict:
    """Wählt die Seite, deren Titel im Ereignistext vorkommt und am spezifischsten (längsten) ist –
    z. B. 'Arecibo-Botschaft' statt 'Radioteleskop'. Fallback: erste Seite."""
    import re as _re
    low = event_text.lower()
    matches = [p for p in pages if p.get("url") and _re.sub(r"\s*\(.*\)$", "", p["title"]).lower() in low]
    return max(matches, key=lambda p: len(p["title"])) if matches else pages[0]


class ResearchAgent(Agent):
    name = "research"

    def __init__(self, ctx: AgentContext, wikipedia: WikipediaClient | None = None):
        super().__init__(ctx)
        self.wiki = wikipedia or WikipediaClient(ctx.settings, ctx.http)

    def trusted(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in self.s.trusted_domains)

    def _store(self, item: ResearchItem) -> ResearchItem:
        item.category = categorize(f"{item.title} {item.summary}")
        item.id = self.memory.add_research(item)
        return item

    # --- Themensuche ----------------------------------------------------------------
    def research_topic(self, topic: str, max_articles: int = 2) -> list[ResearchItem]:
        """Recherche zu einem vorgegebenen Thema (manuell oder aus Kommentaren)."""
        items = []
        for title in self.wiki.search(topic, limit=5):
            art = self.wiki.article(title)
            if not art:
                continue
            ok = self.trusted(art["url"]) and word_count(art["extract"]) >= MIN_WORDS_VERIFIED
            items.append(self._store(ResearchItem(
                title=art["title"], summary=art["extract"], url=art["url"], source="wikipedia", verified=ok,
                verification_note="Wikipedia-API, Artikel abrufbar" if ok else "zu wenig Text oder Domain nicht vertraut")))
            if len(items) >= max_articles:
                break
        self.event("info", f"Recherche '{topic}': {len(items)} Artikel")
        return items

    def discover(self, day: date | None = None, max_items: int = 25) -> list[ResearchItem]:
        """Neue Themen: Wikipedia 'Was geschah am …' plus konfigurierte RSS-Feeds."""
        day = day or date.today()
        found: list[ResearchItem] = []
        try:
            for ev in self.wiki.on_this_day(day):
                if not ev["pages"] or not ev["text"]:
                    continue
                page = most_specific_page(ev["text"], ev["pages"])
                if not page["url"]:
                    continue
                summary = f"Am {day.day}. {MONTHS[day.month - 1]} {ev['year']}: {ev['text']} {page['extract']}".strip()
                verified = self.trusted(page["url"]) and word_count(summary) >= MIN_WORDS_VERIFIED
                found.append(self._store(ResearchItem(
                    title=page["title"], summary=summary, url=page["url"], source="wikipedia_onthisday",
                    published_at=str(ev["year"]), verified=verified,
                    verification_note="Wikipedia-API (Was geschah am …)" if verified else "zu wenig Text")))
                if len(found) >= max_items:
                    break
        except ExternalApiError as exc:
            self.event("warning", f"Wikipedia 'Was geschah am' nicht verfügbar: {exc}")
        for feed in self.s.research_rss_feeds:
            try:
                for it in fetch_feed(self.ctx.http, feed, self.s.http_retries)[:10]:
                    found.append(self._store(self.verify_web(ResearchItem(
                        title=it["title"], summary=it["summary"], url=it["url"], source=urlparse(feed).hostname or "rss",
                        published_at=it["published_at"]))))
            except ExternalApiError as exc:
                self.event("warning", f"RSS-Feed nicht verfügbar ({urlparse(feed).hostname}): {exc}")
        self.event("info", f"Themensuche: {len(found)} Einträge, davon {sum(i.verified for i in found)} verifiziert")
        return found

    def verify_web(self, item: ResearchItem) -> ResearchItem:
        if not self.trusted(item.url):
            item.verified, item.verification_note = False, "Domain nicht auf der Vertrauensliste"
            return item
        try:
            resp = request(self.ctx.http, "GET", item.url, retries=1)
            ok = resp.status_code == 200 and word_count(item.summary) >= 10
            item.verified = ok
            item.verification_note = "Original-URL abrufbar" if ok else f"HTTP {resp.status_code} / zu wenig Text"
        except Exception as exc:  # Netzwerkfehler -> nicht verifiziert, aber kein Abbruch
            item.verified, item.verification_note = False, f"nicht abrufbar: {type(exc).__name__}"
        return item

    # --- Material für das Skript ---------------------------------------------------
    def material(self, items: list[ResearchItem]) -> list[str]:
        """Liefert verifizierte Sätze; Wikipedia-Einträge werden um den Artikelanfang ergänzt."""
        sentences: list[str] = []
        for item in items:
            if not item.verified:
                continue
            texts = [item.summary]
            if item.source.startswith("wikipedia"):
                try:
                    art = self.wiki.article(item.title)
                    if art:
                        texts.append(art["extract"])
                except ExternalApiError as exc:
                    self.event("warning", f"Artikel '{item.title}' nicht abrufbar: {exc}")
            for t in texts:
                for s in split_sentences(t):
                    if s not in sentences:
                        sentences.append(s)
        return sentences
