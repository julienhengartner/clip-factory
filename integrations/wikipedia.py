"""Wikipedia (kostenlos, offizielle APIs): Suche, Artikelauszüge, "Was geschah am ...".

Inhalte stehen unter CC BY-SA – Quellen werden gespeichert und in der Videobeschreibung genannt.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import quote

import httpx

from config import Settings
from core.errors import ExternalApiError
from core.text import clean_research_text
from integrations.http import request


class WikipediaClient:
    def __init__(self, settings: Settings, client: httpx.Client):
        self.s = settings
        self.client = client
        self.lang = settings.research_language
        self.api = f"https://{self.lang}.wikipedia.org/w/api.php"
        self.rest = f"https://{self.lang}.wikipedia.org/api/rest_v1"

    def _get(self, url: str, params: dict | None = None) -> dict:
        resp = request(self.client, "GET", url, params=params, retries=self.s.http_retries)
        if resp.status_code != 200:
            raise ExternalApiError("wikipedia", resp.text[:200], resp.status_code)
        return resp.json()

    def search(self, query: str, limit: int = 5) -> list[str]:
        data = self._get(self.api, {"action": "query", "list": "search", "srsearch": query, "srlimit": limit,
                                    "format": "json", "srnamespace": 0})
        return [hit["title"] for hit in data.get("query", {}).get("search", [])]

    def article(self, title: str, sentences: int = 10) -> dict | None:
        """Gibt {title, url, extract} zurück; None für fehlende Seiten und Begriffsklärungen."""
        data = self._get(self.api, {"action": "query", "prop": "extracts|info|pageprops", "inprop": "url",
                                    "explaintext": 1, "exsentences": sentences, "titles": title, "redirects": 1,
                                    "format": "json"})
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            if "missing" in page or "disambiguation" in page.get("pageprops", {}):
                return None
            extract = clean_research_text(page.get("extract", ""))
            if not extract:
                return None
            return {"title": page["title"], "url": page.get("fullurl") or self.page_url(page["title"]),
                    "extract": extract}
        return None

    def on_this_day(self, day: date) -> list[dict]:
        data = self._get(f"{self.rest}/feed/onthisday/events/{day.month:02d}/{day.day:02d}")
        events = []
        for ev in data.get("events", []):
            pages = [{"title": p.get("titles", {}).get("normalized") or p.get("title", ""),
                      "url": p.get("content_urls", {}).get("desktop", {}).get("page", ""),
                      "extract": clean_research_text(p.get("extract", ""))} for p in ev.get("pages", [])]
            events.append({"year": ev.get("year"), "text": clean_research_text(ev.get("text", "")), "pages": pages})
        return events

    def page_url(self, title: str) -> str:
        return f"https://{self.lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
