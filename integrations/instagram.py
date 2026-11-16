"""Instagram über die offizielle Meta Graph API (nur autorisierter Zugriff, kein Scraping).

Voraussetzungen (siehe README, Abschnitt Instagram):
- Instagram-Professional-Konto (Business oder Creator), verknüpft mit einer Facebook-Seite
- Meta-App mit den Berechtigungen: instagram_basic, instagram_manage_comments, instagram_manage_insights,
  pages_show_list, pages_read_engagement
- Langlebiges Zugriffstoken (META_ACCESS_TOKEN) und die Instagram-Business-Konto-ID (INSTAGRAM_USER_ID)
"""
from __future__ import annotations

import httpx

from config import Settings
from core.errors import ExternalApiError, NotConfiguredError
from integrations.http import request

REQUIRED_PERMISSIONS = ["instagram_basic", "instagram_manage_comments", "instagram_manage_insights",
                        "pages_show_list", "pages_read_engagement"]
MEDIA_INSIGHT_METRICS = ["reach", "saved", "shares", "views"]


class InstagramGraph:
    def __init__(self, settings: Settings, client: httpx.Client):
        self.s, self.client = settings, client
        self.base = settings.meta_graph_base.rstrip("/")

    def missing_requirements(self) -> list[str]:
        missing = []
        if not self.s.meta_access_token:
            missing.append("META_ACCESS_TOKEN")
        if not self.s.instagram_user_id:
            missing.append("INSTAGRAM_USER_ID")
        return missing

    @property
    def configured(self) -> bool:
        return not self.missing_requirements()

    def _get(self, path: str, params: dict | None = None, url: str | None = None) -> dict:
        if not self.configured:
            raise NotConfiguredError("Instagram Graph API", self.missing_requirements() + REQUIRED_PERMISSIONS)
        p = dict(params or {})
        if url is None:
            url = f"{self.base}/{path.lstrip('/')}"
            p["access_token"] = self.s.meta_access_token.get_secret_value()  # type: ignore[union-attr]
        resp = request(self.client, "GET", url, params=p or None, retries=self.s.http_retries)
        data = resp.json() if resp.headers.get("content-type", "").startswith(("application/json", "text/javascript")) else {}
        if resp.status_code != 200 or "error" in data:
            err = data.get("error", {}) if isinstance(data, dict) else {}
            raise ExternalApiError("instagram", err.get("message", resp.text[:200]), resp.status_code,
                                   str(err.get("code")) if err.get("code") is not None else None)
        return data

    def account(self) -> dict:
        return self._get(self.s.instagram_user_id or "", {"fields": "username,followers_count,follows_count,media_count"})

    def media(self, limit: int = 25) -> list[dict]:
        data = self._get(f"{self.s.instagram_user_id}/media", {
            "fields": "id,caption,media_type,media_product_type,timestamp,like_count,comments_count,permalink",
            "limit": limit})
        return data.get("data", [])

    def comments(self, media_id: str, max_pages: int = 5) -> list[dict]:
        out: list[dict] = []
        data = self._get(f"{media_id}/comments", {"fields": "id,text,timestamp,username,like_count", "limit": 50})
        for _ in range(max_pages):
            out.extend(data.get("data", []))
            nxt = data.get("paging", {}).get("next")
            if not nxt:
                break
            data = self._get("", url=nxt)  # next-URL enthält das Token bereits
        return out

    def media_insights(self, media_id: str) -> dict[str, int]:
        """Fragt Metriken einzeln ab – nicht jede Metrik ist für jeden Medientyp/API-Version verfügbar."""
        result: dict[str, int] = {}
        for metric in MEDIA_INSIGHT_METRICS:
            try:
                data = self._get(f"{media_id}/insights", {"metric": metric})
            except ExternalApiError:
                continue
            for entry in data.get("data", []):
                values = entry.get("values") or [{}]
                if isinstance(values[0].get("value"), (int, float)):
                    result[entry["name"]] = int(values[0]["value"])
        return result
