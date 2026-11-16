"""REST-Schnittstelle der Videobibliothek (bewusst klein – kein Dashboard)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from brain.orchestrator import BrainAgent
from core.errors import FactoryError, NotConfiguredError
from storage.models import VideoStatus

PUBLIC_FIELDS = ("id", "topic", "title", "hook", "category", "status", "duration_s", "words", "wpm", "revisions",
                 "voice_provider", "image_provider", "script_provider", "error", "created_at", "approved_at",
                 "published_at", "scheduled_for")


class CreateVideo(BaseModel):
    topic: str | None = Field(default=None, max_length=120)


class Automation(BaseModel):
    enabled: bool


class Schedule(BaseModel):
    at: str | None = Field(default=None, max_length=40)


class Reject(BaseModel):
    reason: str = Field(default="", max_length=300)


def build_router(brain: BrainAgent) -> APIRouter:
    r = APIRouter()

    def video_or_404(video_id: str) -> dict:
        v = brain.memory.get_video(video_id)
        if not v:
            raise HTTPException(404, "Video nicht gefunden")
        return v

    def public(v: dict, detail: bool = False) -> dict:
        out = {k: v.get(k) for k in PUBLIC_FIELDS}
        out["has_video"] = bool(v.get("video_path")) and Path(v["video_path"]).is_file()
        pubs = brain.memory.publications(v["id"])
        out["publication"] = ({k: pubs[-1][k] for k in ("status", "mode", "message", "updated_at")} if pubs else None)
        if v["status"] == VideoStatus.APPROVED.value:
            out["publish_blockers"] = brain.publish_blockers(v)
        qc = v.get("qc") or {}
        out["qc_passed"] = qc.get("passed")
        out["qc_issues"] = [c["detail"] for c in qc.get("checks", []) if not c["passed"]]
        if detail:
            out["script"] = v.get("script")
            out["qc"] = qc
            out["events"] = brain.memory.events(video_id=v["id"], limit=100)
        return out

    def run_production(topic: str | None) -> None:
        try:
            brain.produce(topic=topic or None)
            brain.memory.set_setting("last_production_error", None)
        except Exception as exc:  # noqa: BLE001 – Fehler sichtbar machen statt verschlucken
            brain.memory.set_setting("last_production_error", str(exc)[:300])
            brain.memory.log("error", "api", f"Produktion fehlgeschlagen: {exc}")

    @r.get("/api/state")
    def state() -> dict:
        return {**brain.status(), "last_production_error": brain.memory.get_setting("last_production_error")}

    @r.put("/api/automation")
    def automation(body: Automation) -> dict:
        brain.set_automation(body.enabled)
        return {"automation_enabled": brain.automation_enabled()}

    @r.get("/api/videos")
    def videos() -> list[dict]:
        return [public(v) for v in brain.memory.list_videos(limit=200)]

    @r.post("/api/videos", status_code=202)
    def create(body: CreateVideo, background: BackgroundTasks) -> dict:
        if brain.busy:
            raise HTTPException(409, "Es läuft bereits eine Produktion")
        background.add_task(run_production, (body.topic or "").strip())
        return {"accepted": True}

    @r.get("/api/videos/{video_id}")
    def detail(video_id: str) -> dict:
        return public(video_or_404(video_id), detail=True)

    @r.get("/api/videos/{video_id}/file")
    def file(video_id: str, download: bool = False) -> FileResponse:
        v = video_or_404(video_id)
        if not v.get("video_path") or not Path(v["video_path"]).is_file():
            raise HTTPException(404, "Keine Videodatei")
        name = f"bob-{video_id}.mp4"
        return FileResponse(v["video_path"], media_type="video/mp4", filename=name if download else None,
                            content_disposition_type="attachment" if download else "inline")

    @r.get("/api/videos/{video_id}/thumbnail")
    def thumbnail(video_id: str) -> FileResponse:
        v = video_or_404(video_id)
        if not v.get("thumbnail_path") or not Path(v["thumbnail_path"]).is_file():
            raise HTTPException(404, "Kein Vorschaubild")
        return FileResponse(v["thumbnail_path"], media_type="image/jpeg")

    @r.post("/api/videos/{video_id}/approve")
    def approve(video_id: str) -> dict:
        video_or_404(video_id)
        try:
            return public(brain.approve(video_id))
        except FactoryError as exc:
            raise HTTPException(409, str(exc))

    @r.post("/api/videos/{video_id}/reject")
    def reject(video_id: str, body: Reject | None = None) -> dict:
        video_or_404(video_id)
        try:
            return public(brain.reject(video_id, body.reason if body else ""))
        except FactoryError as exc:
            raise HTTPException(409, str(exc))

    @r.post("/api/videos/{video_id}/schedule")
    def schedule(video_id: str, body: Schedule) -> dict:
        video_or_404(video_id)
        try:
            return public(brain.schedule(video_id, body.at))
        except (FactoryError, ValueError) as exc:
            raise HTTPException(409, str(exc))

    @r.post("/api/videos/{video_id}/publish")
    def publish(video_id: str) -> dict:
        video_or_404(video_id)
        try:
            outcome = brain.publish(video_id)
        except (FactoryError, NotConfiguredError) as exc:
            raise HTTPException(409, str(exc))
        return outcome.model_dump()

    # --- TikTok-Konto verbinden (OAuth) ---------------------------------------------
    @r.get("/oauth/tiktok/start")
    def tiktok_start() -> RedirectResponse:
        try:
            url, state_token = brain.publisher.client.authorize_url()
        except NotConfiguredError as exc:
            raise HTTPException(409, str(exc))
        brain.memory.add_oauth_state(state_token, "tiktok")
        return RedirectResponse(url)

    @r.get("/oauth/tiktok/callback", response_class=HTMLResponse)
    def tiktok_callback(request: Request) -> str:
        q = request.query_params
        if q.get("error"):
            raise HTTPException(400, f"TikTok: {q.get('error_description') or q.get('error')}")
        if not q.get("state") or not brain.memory.consume_oauth_state(q["state"], "tiktok"):
            raise HTTPException(400, "Ungültiger oder abgelaufener OAuth-Status")
        brain.publisher.client.exchange_code(q.get("code", ""))
        brain.memory.log("info", "tiktok", "TikTok-Konto verbunden")
        return "<p style='font-family:sans-serif'>TikTok-Konto verbunden. Dieses Fenster kann geschlossen werden.</p>"

    return r
