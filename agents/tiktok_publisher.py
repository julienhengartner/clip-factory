"""TikTok Publisher Agent: Beschreibung, Hashtags, autorisierter Upload und Statusverfolgung.

Sicherheitsregeln (alle müssen erfüllt sein):
1. Video hat die Qualitätskontrolle bestanden UND wurde von einem Menschen freigegeben (Status approved).
2. BBOB_ALLOW_PUBLISHING=true.
3. TikTok-App-Zugangsdaten und verbundenes Konto (OAuth) vorhanden.
4. Länge erneut per ffprobe >= 60 s.
Standardmodus 'inbox' lädt nur einen Entwurf hoch; 'published' wird erst gesetzt, wenn die API
PUBLISH_COMPLETE meldet.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from agents.base import Agent, AgentContext
from core.errors import FactoryError
from core.text import keywords
from integrations.tiktok import TikTokClient
from storage.database import utcnow
from storage.models import PublishOutcome, VideoStatus
from video_engine.duration import evaluate_length
from video_engine.ffmpeg import probe_duration

BASE_TAGS = ["#bürgermeisterbob", "#wusstestdu", "#lernenmittiktok"]
# auf dem Instagram-Kanal beobachtete Hashtags (16.11.2026)
BOBSTADT_TAGS = ["#bürgermeisterbob", "#bobstadt", "#citybuilder", "#isometric"]
CATEGORY_TAGS = {"technik": "#erfindungen", "wissenschaft": "#wissenschaft", "geschichte": "#geschichte",
                 "politik": "#gemeinde", "kultur": "#kultur", "sport": "#sport", "natur": "#natur"}
FINAL_OK = {"PUBLISH_COMPLETE"}
INBOX_OK = {"SEND_TO_USER_INBOX"}
FAILED = {"FAILED"}


def hashtags(title: str, category: str, script_text: str, max_tags: int = 6) -> list[str]:
    tags = list(BOBSTADT_TAGS if category == "bobstadt" else BASE_TAGS)
    if category in CATEGORY_TAGS:
        tags.append(CATEGORY_TAGS[category])
    for kw in keywords(f"{title} {title} {script_text}", 4):
        tag = "#" + re.sub(r"[^0-9a-zäöüß]", "", kw.lower())
        if len(tag) > 3 and tag not in tags:
            tags.append(tag)
    return tags[:max_tags]


BOBBINGTON_TAGS = ["#bobbington", "#britishcomedy", "#animation", "#3danimation", "#mayor", "#comedy"]


def caption_bobbington(video: dict) -> str:
    ep = (video.get("episode") or {}).get("bobbington", {})
    from bobbington.voices import VOICE_CREDITS
    from bobbington.bible import CAST, SERIES
    models = sorted({CAST[l["speaker"]]["voice"]["model"] for s in ep.get("shots", []) for l in s.get("lines", [])})
    credit = "Voices: Piper TTS – " + "; ".join(VOICE_CREDITS[m].split(" – ", 1)[1] for m in models) if models else ""
    parts = [f"{ep.get('title', video.get('title'))} – {ep.get('logline', '')}".strip(" –"),
             f"Bobbington: {SERIES['tagline']}", credit, " ".join(BOBBINGTON_TAGS)]
    return "\n\n".join(p for p in parts if p)[:2200]


def caption(video: dict) -> str:
    if video.get("category") == "bobbington":
        return caption_bobbington(video)
    script = video.get("script") or {}
    segs = script.get("segments", [])
    cta = next((s["text"] for s in segs if s["role"] == "cta"), "")
    question = cta.split("?")[0] + "?" if "?" in cta else ""
    full = " ".join(s["text"] for s in segs)
    sources = sorted({urlparse(u).hostname for u in script.get("sources", []) if u.startswith("http")})
    src = ("Quellen: " + ", ".join(sources) + (" (Texte: Wikipedia, CC BY-SA)" if any("wikipedia" in s for s in sources) else "")) \
        if sources else ""
    parts = [f"{video.get('title') or video['topic']} – {video.get('hook') or ''}".strip(" –"), question, src,
             " ".join(hashtags(video.get("title") or video["topic"], video.get("category", ""), full))]
    return "\n\n".join(p for p in parts if p)[:2200]


class TikTokPublisherAgent(Agent):
    name = "tiktok_publisher"

    def __init__(self, ctx: AgentContext, client: TikTokClient | None = None):
        super().__init__(ctx)
        self.client = client or TikTokClient(ctx.settings, ctx.tokens, ctx.http)

    def blockers(self, video: dict) -> list[str]:
        reasons = []
        if video["status"] != VideoStatus.APPROVED.value:
            reasons.append(f"Video ist nicht freigegeben (Status: {video['status']})")
        if not self.s.allow_publishing:
            reasons.append("Veröffentlichung deaktiviert (BBOB_ALLOW_PUBLISHING=false)")
        reasons += [f"TikTok: {m}" for m in self.client.missing_requirements()]
        if video.get("video_path") and Path(video["video_path"]).is_file():
            length = evaluate_length(probe_duration(video["video_path"], self.s.ffprobe_bin), self.s)
            if not length.publishable:
                reasons.append(length.message)
        else:
            reasons.append("Videodatei fehlt")
        return reasons

    def publish(self, video: dict) -> PublishOutcome:
        blockers = self.blockers(video)
        if blockers:
            raise FactoryError("Veröffentlichung nicht möglich: " + "; ".join(blockers))
        mode = self.s.tiktok_publish_mode
        text = caption(video)
        privacy = None
        if mode == "direct":
            info = self.client.creator_info()
            options = info.get("privacy_level_options", [])
            privacy = self.s.tiktok_privacy_level
            if options and privacy not in options:
                raise FactoryError(f"Privatsphäre-Stufe {privacy} nicht erlaubt (erlaubt: {options})")
        init = self.client.init_upload(Path(video["video_path"]), mode, title=text, privacy_level=privacy or "SELF_ONLY")
        publish_id, upload_url = init.get("publish_id"), init.get("upload_url")
        if not publish_id or not upload_url:
            raise FactoryError("TikTok-Antwort ohne publish_id/upload_url")
        pub_id = self.memory.add_publication(video["id"], "tiktok", mode, "uploading", publish_id, text, privacy)
        try:
            self.client.upload_file(upload_url, Path(video["video_path"]))
        except Exception as exc:
            self.memory.update_publication(pub_id, status="failed", message=str(exc)[:500])
            self.event("error", f"Upload fehlgeschlagen: {exc}", video["id"])
            raise
        self.memory.update_publication(pub_id, status="processing")
        self.memory.update_video(video["id"], status=VideoStatus.PUBLISHING)
        self.event("info", f"Upload an TikTok abgeschlossen ({mode}), publish_id={publish_id}", video["id"])
        return PublishOutcome(mode=mode, status="processing", publish_id=publish_id,
                              message="Hochgeladen – TikTok verarbeitet das Video.")

    def refresh(self) -> list[dict]:
        """Fragt den Status offener Uploads ab und aktualisiert Videos nur anhand echter API-Antworten."""
        updates = []
        for pub in self.memory.publications(status=["processing", "uploading"]):
            data = self.client.fetch_status(pub["publish_id"])
            status = data.get("status", "")
            if status in FINAL_OK:
                ids = data.get("publicaly_available_post_id") or data.get("publicly_available_post_id") or []
                self.memory.update_publication(pub["id"], status="published", external_id=str(ids[0]) if ids else None,
                                               message=status)
                self.memory.update_video(pub["video_id"], status=VideoStatus.PUBLISHED, published_at=utcnow())
            elif status in INBOX_OK:
                self.memory.update_publication(pub["id"], status="in_inbox", message="Entwurf in der TikTok-Inbox – "
                                               "bitte in der App veröffentlichen")
            elif status in FAILED:
                self.memory.update_publication(pub["id"], status="failed", message=str(data.get("fail_reason")))
                self.memory.update_video(pub["video_id"], status=VideoStatus.APPROVED, error=f"TikTok: {data.get('fail_reason')}")
            updates.append({"publication": pub["id"], "status": status})
        return updates
