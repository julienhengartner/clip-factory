"""Brain Agent: koordiniert alle Agenten, verwaltet das Gedächtnis und steuert die Produktionspipeline.

Pipeline (20 Schritte, jeder wird protokolliert):
 1 Thema wählen  2 Recherche  3 Quellen prüfen  4 Videoidee  5 Hook  6 Skript  7 Längenprüfung
 8 Szenenplan  9 Visuals  10 Voice-over  11 Szenen  12 Schnitt  13 Untertitel  14 Musik (nur lizenziert)
 15 9:16-Render  16 Längenkontrolle  17 Tonprüfung  18 Untertitelprüfung  19 Gesamtprüfung  20 Archiv

Längen-Regelkreis: Skript -> echte Sprachaufnahme -> gemessene Dauer -> bei < 60 s erweitern bzw.
bei > 80 s kürzen -> neu vertonen (max. `max_script_revisions` Durchläufe).
"""
from __future__ import annotations

import json
import math
import re
import shutil
import threading
from pathlib import Path
from typing import Any

import httpx

from agents.base import AgentContext
from agents.comment_analysis import CommentAnalysisAgent
from agents.follower_analytics import FollowerAnalyticsAgent
from agents.hook import HookAgent
from agents.image_generation import ImageGenerationAgent
from agents.instagram_monitor import InstagramMonitorAgent
from agents.quality_control import QualityControlAgent
from agents.research import ResearchAgent
from agents.script_writer import ScriptWriterAgent
from agents.subtitles import SubtitleAgent
from agents.tiktok_publisher import TikTokPublisherAgent
from agents.video_director import VideoDirectorAgent
from agents.video_editing import VideoEditingAgent
from agents.voice import VoiceAgent
from brain.budget import BudgetGuard
from brain.learning import LearningAgent
from brain.memory import Memory
from brain.strategy import Strategy, categorize
from config import Settings, get_settings
from core.errors import FactoryError, InsufficientMaterialError, NotConfiguredError
from core.logging import get_logger, setup_logging
from core.text import similarity
from integrations.http import make_client
from integrations.token_store import TokenStore
from storage.database import Database, utcnow
from storage.models import Idea, PublishOutcome, Script, VideoStatus
from video_engine.duration import LengthVerdict, evaluate_length
from video_engine.ffmpeg import FFmpegError

log = get_logger("brain")


class BrainAgent:
    name = "brain"

    def __init__(self, settings: Settings | None = None, *, http_transport: httpx.BaseTransport | None = None,
                 **agent_overrides: Any):
        self.s = settings or get_settings()
        self.s.ensure_dirs()
        setup_logging(self.s.logs_dir, self.s.secret_values())
        self.db = Database(self.s.db_path)
        self.memory = Memory(self.db)
        self.budget = BudgetGuard(self.s, self.memory)
        self.ctx = AgentContext(settings=self.s, memory=self.memory, budget=self.budget,
                                http=make_client(self.s, http_transport), tokens=TokenStore(self.s.secrets_dir))
        self.strategy = Strategy(self.s, self.memory)
        o = agent_overrides
        self.research = o.get("research") or ResearchAgent(self.ctx)
        self.instagram = o.get("instagram") or InstagramMonitorAgent(self.ctx)
        self.comments = o.get("comments") or CommentAnalysisAgent(self.ctx)
        self.followers = o.get("followers") or FollowerAnalyticsAgent(self.ctx)
        self.hook = o.get("hook") or HookAgent(self.ctx)
        self.writer = o.get("writer") or ScriptWriterAgent(self.ctx, llm=self._llm())
        self.director = o.get("director") or VideoDirectorAgent(self.ctx)
        self.voice = o.get("voice") or VoiceAgent(self.ctx)
        self.images = o.get("images") or ImageGenerationAgent(self.ctx)
        self.editing = o.get("editing") or VideoEditingAgent(self.ctx)
        self.subtitles = o.get("subtitles") or SubtitleAgent(self.ctx)
        self.qc = o.get("qc") or QualityControlAgent(self.ctx)
        self.publisher = o.get("publisher") or TikTokPublisherAgent(self.ctx)
        self.learning = o.get("learning") or LearningAgent(self.memory)
        self._lock = threading.Lock()
        self.recover_interrupted()

    def recover_interrupted(self, max_age_s: int = 3600) -> int:
        """Produktionen, die nach einem Absturz im Status 'producing' hängen, als fehlgeschlagen markieren."""
        from datetime import datetime, timezone
        n = 0
        for v in self.memory.list_videos(status="producing", limit=50):
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(v["updated_at"])).total_seconds()
            if age > max_age_s:
                self._fail(v["id"], "Produktion wurde unterbrochen (Programmabbruch)")
                n += 1
        return n

    def _llm(self):
        if self.s.llm_provider != "openai":
            return None
        try:
            from integrations.openai_api import OpenAIService
            return OpenAIService(self.s, self.budget)
        except NotConfiguredError as exc:
            self.memory.log("warning", self.name, f"Sprachmodell nicht verfügbar, Offline-Autor aktiv: {exc}")
            return None

    # --- Hilfen ----------------------------------------------------------------------
    def _step(self, video_id: str, n: int, message: str, level: str = "info") -> None:
        self.memory.log(level, self.name, f"[{n:02d}] {message}", video_id=video_id)
        getattr(log, "warning" if level == "warning" else "info")(f"{video_id} [{n:02d}] {message}")

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def automation_enabled(self) -> bool:
        return bool(self.memory.get_setting("automation_enabled", False))

    def set_automation(self, enabled: bool) -> None:
        self.memory.set_setting("automation_enabled", bool(enabled))
        self.memory.log("info", self.name, f"Automatische Produktion {'aktiviert' if enabled else 'deaktiviert'}")

    # --- Themenwahl ------------------------------------------------------------------
    def _idea_for_topic(self, topic: str) -> Idea:
        items = [i for i in self.research.research_topic(topic) if i.verified and i.category != "sensibel"]
        if not items:
            raise InsufficientMaterialError(f"Keine verifizierten, geeigneten Quellen zu '{topic}' gefunden")
        for prev in self.memory.produced_topics():
            if similarity(topic, prev) >= 0.5:
                self.memory.log("warning", self.name, f"Thema ähnelt einem früheren Video: '{prev}'")
                break
        main_title = re.sub(r"\s*\([^)]*\)", "", items[0].title).strip() or topic.strip()
        idea = Idea(title=main_title, angle=f"Manuell gewünschtes Thema: {topic.strip()}",
                    category=categorize(" ".join(i.summary for i in items)),
                    research_ids=[i.id for i in items if i.id], origin="manual")
        idea.id = self.memory.add_idea(idea)
        return idea

    def _auto_idea(self, exclude: set[int]) -> Idea | None:
        idea = self.strategy.choose_idea(exclude)
        if idea is None:
            self.strategy.ideas_from_research(self.research.discover())
            idea = self.strategy.choose_idea(exclude)
        return idea

    # --- Produktion ------------------------------------------------------------------
    def produce(self, topic: str | None = None, idea_id: int | None = None, max_idea_attempts: int = 3) -> dict:
        if not self._lock.acquire(blocking=False):
            raise FactoryError("Es läuft bereits eine Produktion")
        try:
            tried: set[int] = set()
            last_error: Exception | None = None
            for _ in range(max_idea_attempts if not (topic or idea_id) else 1):
                if idea_id:
                    idea = self.memory.get_idea(idea_id)
                    if idea is None:
                        raise FactoryError(f"Idee {idea_id} existiert nicht")
                elif topic:
                    idea = self._idea_for_topic(topic)
                else:
                    idea = self._auto_idea(tried)
                    if idea is None:
                        raise InsufficientMaterialError("Keine geeignete neue Idee gefunden")
                tried.add(idea.id)  # type: ignore[arg-type]
                video = self.memory.create_video(idea.title, idea.id, idea.category)
                self._step(video["id"], 1, f"Thema gewählt: {idea.title} ({idea.category}, Herkunft {idea.origin})")
                self.memory.update_idea(idea.id, status="used")
                try:
                    return self._pipeline(video, idea)
                except InsufficientMaterialError as exc:
                    self.memory.update_idea(idea.id, status="rejected")
                    self._fail(video["id"], str(exc))
                    last_error = exc
                    if topic or idea_id:
                        return self.memory.get_video(video["id"])  # type: ignore[return-value]
                except Exception as exc:  # noqa: BLE001 – jeder Fehler wird protokolliert, nichts verschluckt
                    log.exception("Produktion fehlgeschlagen")
                    return self._fail(video["id"], f"{type(exc).__name__}: {exc}")
            raise last_error or InsufficientMaterialError("Keine Idee erfolgreich produzierbar")
        finally:
            self._lock.release()

    def _fail(self, video_id: str, message: str) -> dict:
        self.memory.log("error", self.name, message, video_id=video_id)
        return self.memory.update_video(video_id, status=VideoStatus.FAILED, error=message[:1000])

    def _pipeline(self, video: dict, idea: Idea) -> dict:
        vid = video["id"]
        out = self.s.videos_dir / vid
        work = out / "work"
        style = self.strategy.style()

        items = self.memory.get_research(idea.research_ids)
        self._step(vid, 2, f"Recherche: {len(items)} Quelle(n)")
        verified = [i for i in items if i.verified]
        if not verified:
            raise InsufficientMaterialError("Keine verifizierte Quelle")
        material = self.research.material(verified)
        self._step(vid, 3, f"Quellen geprüft: {len(verified)} verifiziert, {len(material)} Sätze Material")
        self._step(vid, 4, f"Videoidee: {idea.angle}")

        voice_name = self.voice.provider_name
        wpm = self.writer.speech_rate(voice_name)
        context = " ".join(material[:6])
        hook, candidates = self.hook.choose(idea, context, wpm)
        for c in candidates:
            self.memory.add_hook(vid, c.text, c.pattern, c.score, c is hook)
        self._step(vid, 5, f"Hook ({hook.pattern}): {hook.text}")

        target = self.writer.target_words(voice_name)
        script = self.writer.write(idea, material, hook, target, style)
        script.sources = [i.url for i in verified]
        self._step(vid, 6, f"Skript ({script.provider}): {script.word_count} Wörter, Ziel {target} bei {wpm:.0f} wpm")

        scenes, total, revisions = None, 0.0, 0
        for revision in range(self.s.max_script_revisions + 1):
            # Vorab-Schätzung (kostenlos): grob korrigieren, bevor vertont wird
            for _ in range(3):
                est = script.word_count / wpm * 60
                if est < self.s.min_duration_s + 2:
                    script = self.writer.expand(script, idea, material, math.ceil((self.s.target_duration_s - est) * wpm / 60))
                elif est > self.s.ideal_max_duration_s:
                    script = self.writer.shorten(script, idea, math.ceil((est - self.s.target_duration_s) * wpm / 60))
                else:
                    break
            self._step(vid, 7, f"Längenplanung Rev. {revision}: {script.word_count} Wörter ≈ "
                               f"{script.word_count / wpm * 60:.1f} s geschätzt")
            planned = self.director.plan(script, style)
            self._step(vid, 8, f"Szenenplan: {len(planned)} Szenen")
            shutil.rmtree(work / "audio", ignore_errors=True)
            scenes, total, measured = self.voice.synthesize(planned, work / "audio")
            wpm = measured or wpm
            length = evaluate_length(total, self.s)
            self._step(vid, 10, f"Voice-over ({voice_name}): {total:.2f} s gemessen, {measured:.0f} wpm – {length.message}")
            revisions = revision
            if length.publishable:
                break
            if revision == self.s.max_script_revisions:
                raise FactoryError(f"Länge nach {revision} Überarbeitungen nicht erreicht: {length.message}")
            if length.verdict == LengthVerdict.TOO_SHORT:
                extra = math.ceil(length.missing_s * wpm / 60) + 3
                script = self.writer.expand(script, idea, material, extra)
                self._step(vid, 7, f"Zu kurz – Skript um ca. {extra} Wörter erweitert", "warning")
            else:
                excess = math.ceil((total - self.s.target_duration_s) * wpm / 60)
                script = self.writer.shorten(script, idea, excess)
                self._step(vid, 7, f"Zu lang – Skript um ca. {excess} Wörter gekürzt", "warning")
        assert scenes is not None
        self.memory.update_video(vid, title=script.title, hook=hook.text, hook_pattern=hook.pattern,
                                 script_json=script.model_dump(), words=script.word_count, wpm=wpm,
                                 voice_provider=voice_name, script_provider=script.provider, revisions=revisions)

        scenes = self.editing.cut(scenes)
        self._step(vid, 11, f"Szenen geschnitten: {sum(len(s.shots) for s in scenes)} Shots "
                            f"(max. {self.s.max_shot_s} s pro Bild)")
        scenes = self.images.create(scenes, work / "images", script.title)
        self._step(vid, 9, f"Visuals erzeugt ({self.images.provider})")
        cues, ass, srt = self.subtitles.build(scenes, out)
        self._step(vid, 13, f"Untertitel: {len(cues)} Einblendungen")

        final = thumb = music = None
        for attempt in range(1, self.s.max_render_attempts + 1):
            try:
                final, thumb, music = self.editing.assemble(scenes, ass, out, seed=vid)
                break
            except FFmpegError as exc:
                self._step(vid, 15, f"Render-Versuch {attempt} fehlgeschlagen: {exc}", "warning")
                self.memory.update_video(vid, render_attempts=attempt)
                if attempt == self.s.max_render_attempts:
                    raise
        self._step(vid, 14, f"Musik: {Path(music).name if music else 'keine (nur lizenzierte Musik erlaubt)'}")
        self._step(vid, 15, f"9:16-Video gerendert: {final.name}")

        report = self.qc.check(final, scenes, script, cues, sources_verified=bool(verified))
        for name, n in (("laenge_minimum", 16), ("lautheit", 17), ("untertitel_vollstaendig", 18)):
            c = report.get(name)
            if c:
                self._step(vid, n, f"{name}: {'OK' if c.passed else 'FEHLER'} – {c.detail}", "info" if c.passed else "warning")
        status = VideoStatus.READY if report.passed else VideoStatus.QC_FAILED
        self._step(vid, 19, f"Gesamtprüfung: {'bestanden' if report.passed else 'NICHT bestanden'} "
                            f"({len(report.errors)} Fehler, {len(report.warnings)} Warnungen)",
                   "info" if report.passed else "warning")

        (out / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
        (out / "qc.json").write_text(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "sources.txt").write_text("\n".join(script.sources) + "\n", encoding="utf-8")
        shutil.rmtree(work, ignore_errors=True)  # Zwischendateien entfernen, Archiv bleibt
        scenes_light = [s.model_dump(exclude={"words", "audio_path"}) for s in scenes]
        for s in scenes_light:
            s["shots"] = [{k: v for k, v in sh.items() if k != "image_path"} for sh in s["shots"]]
        video = self.memory.update_video(
            vid, status=status, video_path=str(final), thumbnail_path=str(thumb), duration_s=report.get("laenge_minimum").value,
            qc_json={"passed": report.passed, "checks": [c.model_dump() for c in report.checks]},
            scenes_json=scenes_light, image_provider=self.images.provider,
            error=None if report.passed else "; ".join(c.detail for c in report.errors))
        self._step(vid, 20, f"Archiviert in {out}")
        return video

    # --- Freigabe & Veröffentlichung -------------------------------------------------
    def approve(self, video_id: str) -> dict:
        v = self.memory.get_video(video_id)
        if not v:
            raise KeyError(video_id)
        if v["status"] != VideoStatus.READY.value:
            raise FactoryError(f"Nur geprüfte Videos (Status 'ready') können freigegeben werden – aktuell '{v['status']}'")
        self.memory.log("info", self.name, "Video freigegeben", video_id=video_id)
        return self.memory.update_video(video_id, status=VideoStatus.APPROVED, approved_at=utcnow())

    def reject(self, video_id: str, reason: str = "") -> dict:
        v = self.memory.get_video(video_id)
        if not v:
            raise KeyError(video_id)
        if v["status"] not in (VideoStatus.READY.value, VideoStatus.APPROVED.value, VideoStatus.QC_FAILED.value):
            raise FactoryError(f"Video im Status '{v['status']}' kann nicht abgelehnt werden")
        self.memory.log("info", self.name, f"Video abgelehnt: {reason or 'ohne Begründung'}", video_id=video_id)
        return self.memory.update_video(video_id, status=VideoStatus.REJECTED, error=reason or None)

    def publish(self, video_id: str) -> PublishOutcome:
        v = self.memory.get_video(video_id)
        if not v:
            raise KeyError(video_id)
        return self.publisher.publish(v)

    def publish_blockers(self, video: dict) -> list[str]:
        return self.publisher.blockers(video)

    # --- Analyse & Lernen ------------------------------------------------------------
    def collect_tiktok_performance(self) -> dict:
        if not self.publisher.client.connected:
            return {"status": "not_configured", "missing": self.publisher.client.missing_requirements()}
        by_ext = {p["external_id"]: p["video_id"] for p in self.memory.publications() if p.get("external_id")}
        n = 0
        for v in self.publisher.client.list_videos():
            self.memory.add_performance("tiktok", str(v["id"]), by_ext.get(str(v["id"])), views=v.get("view_count"),
                                        likes=v.get("like_count"), comments=v.get("comment_count"),
                                        shares=v.get("share_count"))
            n += 1
        return {"status": "ok", "videos": n}

    def status(self) -> dict:
        return {
            "automation_enabled": self.automation_enabled(),
            "producing": self.busy,
            "publishing_allowed": self.s.allow_publishing,
            "paid_apis_allowed": self.s.allow_paid_apis,
            "publish_mode": self.s.tiktok_publish_mode,
            "providers": {"voice": self.s.voice_provider, "images": self.s.image_provider, "script": self.s.llm_provider},
            "tiktok_missing": self.publisher.client.missing_requirements(),
            "instagram_missing": self.instagram.graph.missing_requirements(),
            "style_profile": self.strategy.style().source,
            "videos_today": self.memory.videos_created_today(),
            "max_videos_per_day": self.s.max_videos_per_day,
        }

    def backup(self) -> Path:
        path = self.db.backup(self.s.backups_dir, self.s.backups_keep)
        self.memory.log("info", self.name, f"Gedächtnis gesichert: {path.name}")
        return path
