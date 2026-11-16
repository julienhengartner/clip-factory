"""TikTok – offizielle Content Posting API (v2) und Display API, inkl. OAuth 2.0.

Modi:
- inbox  (Standard): Video wird als Entwurf in die TikTok-Inbox des Kontos geladen. Die Veröffentlichung
         erfolgt manuell in der TikTok-App. Scope: video.upload
- direct: Direktveröffentlichung. Erfordert Scope video.publish und – für öffentliche Sichtbarkeit – eine
         erfolgreich geprüfte App (Audit). Ungeprüfte Apps dürfen nur SELF_ONLY (privat) posten.

Hinweis: Gegen die offizielle Dokumentation implementiert und mit simulierten HTTP-Antworten getestet.
Ein Live-Test ist erst mit echten App-Zugangsdaten möglich.
"""
from __future__ import annotations

import math
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from config import Settings
from core.errors import ExternalApiError, NotConfiguredError
from integrations.http import request
from integrations.token_store import TokenStore

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com"
TOKEN_NAME = "tiktok"
SCOPES = {"inbox": ["user.info.basic", "video.upload", "video.list"],
          "direct": ["user.info.basic", "video.publish", "video.list"]}

MIN_CHUNK = 5 * 1024 * 1024
MAX_CHUNK = 64 * 1024 * 1024
DEFAULT_CHUNK = 10 * 1024 * 1024


def chunk_plan(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) gemäss TikTok-Regeln: <=64 MB in einem Stück, sonst 10-MB-Teile,
    wobei der letzte Teil den Rest aufnimmt."""
    if size <= 0:
        raise ValueError("Leere Videodatei")
    if size <= MAX_CHUNK:
        return size, 1
    count = math.floor(size / DEFAULT_CHUNK)
    return DEFAULT_CHUNK, count


class TikTokClient:
    def __init__(self, settings: Settings, tokens: TokenStore, client: httpx.Client, clock=time.time):
        self.s, self.tokens, self.client, self.clock = settings, tokens, client, clock

    # --- Konfiguration --------------------------------------------------------------
    def missing_requirements(self) -> list[str]:
        missing = [n for n, v in (("TIKTOK_CLIENT_KEY", self.s.tiktok_client_key),
                                  ("TIKTOK_CLIENT_SECRET", self.s.tiktok_client_secret),
                                  ("TIKTOK_REDIRECT_URI", self.s.tiktok_redirect_uri)) if not v]
        if not missing and not self.tokens.load(TOKEN_NAME):
            missing.append("TikTok-Konto verbinden (OAuth)")
        return missing

    @property
    def connected(self) -> bool:
        return not self.missing_requirements()

    def _require_app(self) -> None:
        missing = [m for m in self.missing_requirements() if m.startswith("TIKTOK_")]
        if missing:
            raise NotConfiguredError("TikTok", missing)

    # --- OAuth ------------------------------------------------------------------------
    def authorize_url(self, state: str | None = None) -> tuple[str, str]:
        self._require_app()
        state = state or secrets.token_urlsafe(24)
        params = {"client_key": self.s.tiktok_client_key, "response_type": "code",
                  "scope": ",".join(SCOPES[self.s.tiktok_publish_mode]),
                  "redirect_uri": self.s.tiktok_redirect_uri, "state": state}
        return f"{AUTH_URL}?{urlencode(params)}", state

    def _token_request(self, data: dict) -> dict:
        resp = request(self.client, "POST", f"{API}/v2/oauth/token/", data=data, retries=self.s.http_retries,
                       headers={"Content-Type": "application/x-www-form-urlencoded"})
        body = resp.json() if resp.content else {}
        if resp.status_code != 200 or "access_token" not in body:
            raise ExternalApiError("tiktok", body.get("error_description") or body.get("error") or "Token-Anfrage fehlgeschlagen",
                                   resp.status_code, body.get("error"))
        now = self.clock()
        token = {"access_token": body["access_token"], "refresh_token": body.get("refresh_token"),
                 "open_id": body.get("open_id"), "scope": body.get("scope"),
                 "expires_at": now + int(body.get("expires_in", 0)),
                 "refresh_expires_at": now + int(body.get("refresh_expires_in", 0))}
        self.tokens.save(TOKEN_NAME, token)
        return token

    def exchange_code(self, code: str) -> dict:
        self._require_app()
        return self._token_request({"client_key": self.s.tiktok_client_key,
                                    "client_secret": self.s.tiktok_client_secret.get_secret_value(),  # type: ignore[union-attr]
                                    "code": code, "grant_type": "authorization_code",
                                    "redirect_uri": self.s.tiktok_redirect_uri})

    def access_token(self) -> str:
        self._require_app()
        token = self.tokens.load(TOKEN_NAME)
        if not token:
            raise NotConfiguredError("TikTok", ["TikTok-Konto verbinden (OAuth)"])
        if token["expires_at"] - 300 < self.clock():
            if not token.get("refresh_token") or token.get("refresh_expires_at", 0) < self.clock():
                raise NotConfiguredError("TikTok", ["TikTok-Konto erneut verbinden (Token abgelaufen)"])
            token = self._token_request({"client_key": self.s.tiktok_client_key,
                                         "client_secret": self.s.tiktok_client_secret.get_secret_value(),  # type: ignore[union-attr]
                                         "grant_type": "refresh_token", "refresh_token": token["refresh_token"]})
        return token["access_token"]

    # --- API-Aufrufe -----------------------------------------------------------------
    def _api(self, path: str, json_body: dict | None = None, params: dict | None = None) -> dict:
        resp = request(self.client, "POST", f"{API}{path}", json=json_body or {}, params=params,
                       retries=self.s.http_retries,
                       headers={"Authorization": f"Bearer {self.access_token()}",
                                "Content-Type": "application/json; charset=UTF-8"})
        try:
            body = resp.json()
        except ValueError:
            raise ExternalApiError("tiktok", resp.text[:200], resp.status_code)
        err = body.get("error", {})
        if resp.status_code != 200 or err.get("code") not in (None, "ok"):
            raise ExternalApiError("tiktok", err.get("message") or "Unbekannter Fehler", resp.status_code, err.get("code"))
        return body.get("data", {})

    def creator_info(self) -> dict:
        return self._api("/v2/post/publish/creator_info/query/")

    def init_upload(self, video_path: Path, mode: str, title: str = "", privacy_level: str = "SELF_ONLY") -> dict:
        size = Path(video_path).stat().st_size
        chunk_size, count = chunk_plan(size)
        source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk_size, "total_chunk_count": count}
        if mode == "inbox":
            return self._api("/v2/post/publish/inbox/video/init/", {"source_info": source})
        if mode == "direct":
            post_info = {"title": title[:2200], "privacy_level": privacy_level, "disable_duet": False,
                         "disable_comment": False, "disable_stitch": False, "video_cover_timestamp_ms": 1000}
            return self._api("/v2/post/publish/video/init/", {"post_info": post_info, "source_info": source})
        raise ValueError(f"Unbekannter Modus: {mode}")

    def upload_file(self, upload_url: str, video_path: Path) -> None:
        data = Path(video_path).read_bytes()
        size = len(data)
        chunk_size, count = chunk_plan(size)
        for i in range(count):
            start = i * chunk_size
            end = size - 1 if i == count - 1 else start + chunk_size - 1
            resp = request(self.client, "PUT", upload_url, content=data[start:end + 1], retries=self.s.http_retries,
                           headers={"Content-Type": "video/mp4", "Content-Length": str(end - start + 1),
                                    "Content-Range": f"bytes {start}-{end}/{size}"})
            if resp.status_code not in (200, 201, 206):
                raise ExternalApiError("tiktok", f"Upload-Teil {i + 1}/{count} fehlgeschlagen", resp.status_code)

    def fetch_status(self, publish_id: str) -> dict:
        return self._api("/v2/post/publish/status/fetch/", {"publish_id": publish_id})

    def list_videos(self, max_count: int = 20) -> list[dict]:
        data = self._api("/v2/video/list/", {"max_count": max_count},
                         params={"fields": "id,title,create_time,view_count,like_count,comment_count,share_count"})
        return data.get("videos", [])
