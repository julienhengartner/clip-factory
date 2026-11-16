"""RSS-2.0- und Atom-Feeds lesen (offizielle, öffentlich angebotene Feeds – kein Scraping)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from core.errors import ExternalApiError
from core.text import clean_research_text
from integrations.http import request

_ATOM = "{http://www.w3.org/2005/Atom}"


def parse_feed(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        items.append({"title": (it.findtext("title") or "").strip(), "url": (it.findtext("link") or "").strip(),
                      "summary": clean_research_text(it.findtext("description") or ""),
                      "published_at": it.findtext("pubDate")})
    for entry in root.iter(f"{_ATOM}entry"):
        link = entry.find(f"{_ATOM}link")
        items.append({"title": (entry.findtext(f"{_ATOM}title") or "").strip(),
                      "url": link.get("href", "") if link is not None else "",
                      "summary": clean_research_text(entry.findtext(f"{_ATOM}summary") or
                                                     entry.findtext(f"{_ATOM}content") or ""),
                      "published_at": entry.findtext(f"{_ATOM}updated")})
    return [i for i in items if i["title"] and i["url"]]


def fetch_feed(client: httpx.Client, url: str, retries: int = 2) -> list[dict]:
    resp = request(client, "GET", url, retries=retries)
    if resp.status_code != 200:
        raise ExternalApiError("rss", f"Feed {url} nicht abrufbar", resp.status_code)
    return parse_feed(resp.text)
