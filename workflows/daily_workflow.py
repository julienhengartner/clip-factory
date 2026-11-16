"""Täglicher Ablauf (Start per Windows-Aufgabenplanung um 08:00, später cron/systemd auf Ubuntu).

  1 Instagram-Kommentare/Kennzahlen (wenn autorisiert)   6 Lernen aus Ergebnissen
  2 Kommentare analysieren                                7 Themen recherchieren, Ideen bilden
  3 Follower-Bericht                                      8 Video(s) produzieren (Tageskontingent!)
  4 TikTok-Uploadstatus aktualisieren                     9 freigegebene Videos veröffentlichen (nur wenn erlaubt)
  5 TikTok-Performance abrufen                           10 Gedächtnis sichern

Schutz: Dateisperre gegen Doppelstarts, Tageskontingent (max_videos_per_day, auch fehlgeschlagene
Produktionen zählen), höchstens eine Wiederholung bei vorübergehenden Netzwerkfehlern, jeder Schritt
läuft unabhängig weiter, wenn ein anderer fehlschlägt. Ohne aktivierte Automatik passiert nichts.

Aufruf:  python -m workflows.daily_workflow [--force]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from brain.orchestrator import BrainAgent
from core.errors import ExternalApiError, FactoryError, NotConfiguredError
from core.logging import get_logger

log = get_logger("daily")
LOCK_STALE_S = 3 * 3600


class RunLock:
    def __init__(self, path: Path):
        self.path = path
        self.acquired = False

    def __enter__(self) -> "RunLock":
        if self.path.exists() and time.time() - self.path.stat().st_mtime > LOCK_STALE_S:
            self.path.unlink(missing_ok=True)  # verwaiste Sperre nach Absturz
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self.acquired = True
        except FileExistsError:
            self.acquired = False
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)


def transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    return isinstance(exc, ExternalApiError) and (exc.status is None or exc.status >= 500 or exc.status == 429)


def with_retry(fn: Callable[[], Any], attempts: int = 2, delay_s: float = 30,
               sleep: Callable[[float], None] = time.sleep) -> Any:
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            if i + 1 >= attempts or not transient(exc):
                raise
            log.warning("Vorübergehender Fehler (%s), neuer Versuch in %ss", exc, delay_s)
            sleep(delay_s)


class DailyWorkflow:
    def __init__(self, brain: BrainAgent, sleep: Callable[[float], None] = time.sleep):
        self.brain = brain
        self.sleep = sleep

    def _research(self) -> dict:
        b = self.brain
        new = b.strategy.ideas_from_research(b.research.discover())
        from_comments = []
        for kw in (b.memory.get_insight("audience", "requests") or [])[:2]:
            items = b.research.research_topic(kw, max_articles=1)
            from_comments += b.strategy.ideas_from_research(items, origin="comment")
        return {"new_ideas": len(new), "comment_ideas": len(from_comments)}

    def _produce(self) -> dict:
        b = self.brain
        remaining = b.s.max_videos_per_day - b.memory.videos_created_today()
        produced = []
        for _ in range(max(0, remaining)):
            v = b.produce()
            produced.append({"id": v["id"], "status": v["status"], "duration_s": v.get("duration_s")})
        return {"remaining_before": remaining, "videos": produced}

    def _publish(self) -> dict:
        b = self.brain
        if not b.s.allow_publishing:
            return {"status": "disabled"}
        results = []
        for v in b.memory.list_videos(status="approved"):
            if b.publish_blockers(v):
                continue
            outcome = b.publish(v["id"])
            results.append({"id": v["id"], "status": outcome.status})
        return {"published": results}

    def _tiktok_status(self) -> dict:
        client = self.brain.publisher.client
        if not client.connected:
            return {"status": "not_configured", "missing": client.missing_requirements()}
        return {"updates": self.brain.publisher.refresh()}

    def steps(self) -> list[tuple[str, Callable[[], Any]]]:
        b = self.brain
        return [
            ("instagram", lambda: b.instagram.run()),
            ("comments", lambda: {**b.comments.analyze_pending(), "requests": b.comments.audience_requests()}),
            ("followers", lambda: b.followers.report("instagram")),
            ("tiktok_status", self._tiktok_status),
            ("performance", b.collect_tiktok_performance),
            ("learning", b.learning.update),
            ("research", self._research),
            ("produce", self._produce),
            ("publish", self._publish),
            ("backup", lambda: {"file": b.backup().name}),
        ]

    def run(self, force: bool = False) -> dict:
        b = self.brain
        if not force and not b.automation_enabled():
            b.memory.log("info", "daily", "Automatik deaktiviert – täglicher Lauf übersprungen")
            return {"status": "skipped", "reason": "automation_disabled"}
        with RunLock(b.s.data_dir / "daily.lock") as lock:
            if not lock.acquired:
                b.memory.log("warning", "daily", "Täglicher Lauf läuft bereits – Doppelstart verhindert")
                return {"status": "skipped", "reason": "already_running"}
            run_id = b.memory.start_run("daily")
            summary: dict[str, Any] = {}
            errors = 0
            for name, fn in self.steps():
                try:
                    summary[name] = with_retry(fn, sleep=self.sleep)
                except NotConfiguredError as exc:
                    summary[name] = {"status": "not_configured", "missing": exc.missing}
                except (FactoryError, ExternalApiError, httpx.HTTPError, OSError) as exc:
                    errors += 1
                    summary[name] = {"status": "error", "error": str(exc)[:500]}
                    b.memory.log("error", "daily", f"Schritt {name} fehlgeschlagen: {exc}", run_id=run_id)
                except Exception as exc:  # noqa: BLE001 – unerwartet, aber Lauf soll weitergehen
                    errors += 1
                    log.exception("Unerwarteter Fehler in Schritt %s", name)
                    summary[name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:500]}
                    b.memory.log("error", "daily", f"Schritt {name}: {type(exc).__name__}: {exc}", run_id=run_id)
            status = "ok" if errors == 0 else "partial"
            b.memory.finish_run(run_id, status, summary)
            return {"status": status, "run_id": run_id, "summary": summary}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Täglicher Ablauf der BürgermeisterBob Video Factory")
    p.add_argument("--force", action="store_true", help="auch ausführen, wenn die Automatik deaktiviert ist")
    args = p.parse_args(argv)
    result = DailyWorkflow(BrainAgent()).run(force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] in ("ok", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
