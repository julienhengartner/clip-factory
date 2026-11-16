"""HTTP-Hilfen: gemeinsamer Client, begrenzte Wiederholungen, keine Geheimnisse in Logs."""
from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from config import Settings
from core.logging import get_logger

log = get_logger("http")

RETRY_STATUS = {429, 500, 502, 503, 504}


def make_client(settings: Settings, transport: httpx.BaseTransport | None = None, timeout: float = 30) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": settings.http_user_agent}, timeout=timeout,
                        follow_redirects=True, transport=transport)


def _safe_url(url: str | httpx.URL) -> str:
    u = httpx.URL(str(url))
    return str(u.copy_with(query=None))  # Query-Parameter können Tokens enthalten


def request(client: httpx.Client, method: str, url: str, *, retries: int = 2, backoff_s: float = 1.5,
            sleep: Callable[[float], None] = time.sleep, **kwargs: Any) -> httpx.Response:
    """Sendet eine Anfrage; wiederholt bei Netzwerkfehlern, 429 und 5xx höchstens `retries`-mal."""
    attempt = 0
    while True:
        try:
            resp = client.request(method, url, **kwargs)
            if resp.status_code not in RETRY_STATUS or attempt >= retries:
                return resp
            wait = float(resp.headers.get("Retry-After", backoff_s * (2 ** attempt))) if resp.status_code == 429 \
                else backoff_s * (2 ** attempt)
            log.warning("%s %s -> HTTP %s, neuer Versuch in %.1fs", method, _safe_url(url), resp.status_code, wait)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt >= retries:
                raise
            wait = backoff_s * (2 ** attempt)
            log.warning("%s %s -> %s, neuer Versuch in %.1fs", method, _safe_url(url), type(exc).__name__, wait)
        attempt += 1
        sleep(min(wait, 60))
