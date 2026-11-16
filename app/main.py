"""Einstiegspunkt: Web-Oberfläche (FastAPI) und Kommandozeile.

    python -m app.main serve            Oberfläche starten (http://127.0.0.1:8000)
    python -m app.main produce [THEMA]  ein Video erzeugen
    python -m app.main daily [--force]  täglichen Ablauf einmal ausführen
    python -m app.main status           Systemstatus
    python -m app.main backup           Gedächtnis sichern
    python -m app.main tiktok-auth      TikTok-Konto verbinden (Code manuell einfügen)
"""
from __future__ import annotations

import argparse
import threading
from contextlib import asynccontextmanager
import hmac
import ipaddress
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from app.api import build_router
from brain.city import fmt_eur
from brain.orchestrator import BrainAgent
from config import Settings, get_settings

STATIC = Path(__file__).parent / "static"
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def is_loopback(host: str) -> bool:
    if host in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def create_app(settings: Settings | None = None, brain: BrainAgent | None = None) -> FastAPI:
    brain = brain or BrainAgent(settings)
    s = brain.s
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Solange die Oberfläche läuft: alle 5 Minuten geplante Veröffentlichungen prüfen (nur wenn erlaubt)."""
        stop = threading.Event()
        if s.allow_publishing:
            def loop() -> None:
                while not stop.wait(300):
                    try:
                        brain.publish_due()
                    except Exception as exc:  # noqa: BLE001
                        brain.memory.log("error", "scheduler", f"Prüfung geplanter Veröffentlichungen: {exc}")
            threading.Thread(target=loop, name="publish-timer", daemon=True).start()
        yield
        stop.set()

    app = FastAPI(title="BürgermeisterBob Video Factory", version="0.3.0", docs_url=None, redoc_url=None,
                  lifespan=lifespan)
    app.state.brain = brain
    token = s.app_token.get_secret_value() if s.app_token else None

    @app.middleware("http")
    async def protect(request: Request, call_next):
        path = request.url.path
        if token:
            supplied = request.headers.get("authorization", "").removeprefix("Bearer ") or \
                request.cookies.get("bbob_token") or request.query_params.get("token") or ""
            if not hmac.compare_digest(supplied, token):
                return JSONResponse({"detail": "Nicht autorisiert"}, status_code=401)
        # CSRF-Schutz: verändernde API-Aufrufe brauchen einen eigenen Header (erzwingt CORS-Preflight)
        if request.method in MUTATING and path.startswith("/api/") and request.headers.get("x-bbob") != "1":
            return JSONResponse({"detail": "Fehlender X-BBob-Header"}, status_code=403)
        response = await call_next(request)
        if token and request.query_params.get("token") == token:
            response.set_cookie("bbob_token", token, httponly=True, samesite="strict")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.include_router(build_router(brain))

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", media_type="text/html")

    return app


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="bbob", description="BürgermeisterBob AI Video Factory")
    sub = p.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve")
    sv.add_argument("--host")
    sv.add_argument("--port", type=int)
    pr = sub.add_parser("produce")
    pr.add_argument("topic", nargs="?")
    dl = sub.add_parser("daily")
    dl.add_argument("--force", action="store_true")
    sub.add_parser("status")
    ct = sub.add_parser("city", help="Bobstadt-Stadtstand anzeigen und pflegen")
    ct.add_argument("--einwohner", type=int, help="aktuelle Followerzahl = Einwohner")
    ct.add_argument("--ausgaben-korrektur", type=int, help="Euro, um die Ausgaben an die echten Kanalzahlen anzugleichen")
    ct.add_argument("--bestaetigen", action="store_true", help="Startbestand und Zahlen als korrekt bestätigen")
    sub.add_parser("publish-due", help="fällige freigegebene Videos veröffentlichen (nur wenn erlaubt)")
    sub.add_parser("backup")
    sub.add_parser("tiktok-auth")
    args = p.parse_args(argv)

    s = get_settings()
    if args.cmd == "serve":
        host, port = args.host or s.app_host, args.port or s.app_port
        if not is_loopback(host) and not s.app_token:
            print("Abbruch: Für eine Bindung ausserhalb von localhost muss BBOB_APP_TOKEN gesetzt sein.")
            return 2
        import uvicorn
        uvicorn.run(create_app(s), host=host, port=port, log_level="warning")
        return 0

    brain = BrainAgent(s)
    if args.cmd == "produce":
        v = brain.produce(topic=args.topic)
        _print({k: v.get(k) for k in ("id", "status", "title", "duration_s", "video_path", "error")})
        return 0 if v["status"] in ("ready",) else 1
    if args.cmd == "daily":
        from workflows.daily_workflow import DailyWorkflow
        result = DailyWorkflow(brain).run(force=args.force)
        _print(result)
        return 0 if result["status"] in ("ok", "skipped") else 1
    if args.cmd == "status":
        _print({**brain.status(), "ffmpeg": shutil.which(s.ffmpeg_bin), "database": str(s.db_path),
                "learned_speech_rates": brain.memory.insights("speech_rate"),
                "recommendations": brain.memory.get_insight("strategy", "recommendations")})
        return 0
    if args.cmd == "city":
        if args.einwohner is not None:
            brain.city.set_residents(args.einwohner)
        if args.ausgaben_korrektur is not None:
            brain.city.set_spent_adjust(args.ausgaben_korrektur)
        if args.bestaetigen:
            brain.city.confirm()
        st = brain.city.state()
        _print({"einwohner": st.residents, "quelle": st.residents_source, "budget_eur": st.budget_eur,
                "ausgaben_eur": st.spent_eur, "kasse_eur": st.available_eur, "bestaetigt": st.confirmed,
                "gebaeude": [f"{b['name']} ({fmt_eur(b['cost_eur'])}){'' if b['confirmed'] else ' – unbestätigt'}"
                             for b in st.buildings if b["status"] == "built"],
                "wuensche": [(p["value"], p["votes"]) for p in brain.memory.proposals("building")[:5]]})
        return 0
    if args.cmd == "publish-due":
        _print(brain.publish_due())
        return 0
    if args.cmd == "backup":
        print(brain.backup())
        return 0
    if args.cmd == "tiktok-auth":
        client = brain.publisher.client
        url, state = client.authorize_url()
        brain.memory.add_oauth_state(state, "tiktok")
        print("1. Diese Adresse im Browser öffnen und den Zugriff erlauben:\n\n" + url + "\n")
        redirected = input("2. Die vollständige Adresse, auf die TikTok weiterleitet, hier einfügen: ").strip()
        q = parse_qs(urlparse(redirected).query)
        if q.get("state", [""])[0] != state or not brain.memory.consume_oauth_state(state, "tiktok"):
            print("Abbruch: OAuth-Status stimmt nicht überein.")
            return 1
        client.exchange_code(q.get("code", [""])[0])
        print("TikTok-Konto verbunden.")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
