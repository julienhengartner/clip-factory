import pytest
from fastapi.testclient import TestClient

from app.main import create_app, is_loopback
from brain.orchestrator import BrainAgent
from core.errors import InsufficientMaterialError
from tests.conftest import make_settings
from tests.fakes import wiki_transport
from workflows.daily_workflow import DailyWorkflow, RunLock, with_retry
from core.errors import ExternalApiError


@pytest.fixture
def brain(tmp_path):
    return BrainAgent(make_settings(tmp_path), http_transport=wiki_transport({}))


# --- Täglicher Ablauf ----------------------------------------------------------------------
def test_daily_skips_when_automation_disabled(brain):
    assert DailyWorkflow(brain).run()["reason"] == "automation_disabled"


def test_daily_runs_all_steps_and_respects_quota(brain, monkeypatch):
    brain.set_automation(True)
    produced = []

    def fake_produce(topic=None, idea_id=None):
        v = brain.memory.create_video("Fake")
        produced.append(v["id"])
        return brain.memory.update_video(v["id"], status="ready", duration_s=66)
    monkeypatch.setattr(brain, "produce", fake_produce)
    result = DailyWorkflow(brain, sleep=lambda s: None).run()
    s = result["summary"]
    assert s["instagram"]["status"] == "not_configured" and s["tiktok_status"]["status"] == "not_configured"
    assert s["produce"]["videos"][0]["status"] == "ready" and s["publish"] == {"status": "disabled"}
    assert s["backup"]["file"].startswith("brain-")
    # zweiter Lauf am selben Tag: Kontingent (1) erschöpft -> keine weitere Produktion
    again = DailyWorkflow(brain, sleep=lambda s: None).run()
    assert again["summary"]["produce"]["videos"] == [] and len(produced) == 1
    assert brain.memory.runs()[0]["status"] == "ok"


def test_daily_continues_after_step_error(brain, monkeypatch):
    def boom(*a, **k):
        raise InsufficientMaterialError("keine Idee")
    monkeypatch.setattr(brain, "produce", boom)
    result = DailyWorkflow(brain, sleep=lambda s: None).run(force=True)
    assert result["status"] == "partial" and result["summary"]["produce"]["status"] == "error"
    assert "file" in result["summary"]["backup"]  # nachfolgende Schritte liefen weiter
    assert any("produce" in e["message"] for e in brain.memory.events(level="error"))


def test_run_lock_prevents_parallel_runs(tmp_path):
    with RunLock(tmp_path / "x.lock") as a:
        with RunLock(tmp_path / "x.lock") as b:
            assert a.acquired and not b.acquired


def test_retry_only_transient():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise ExternalApiError("x", "Serverfehler", 503)
        return "ok"
    assert with_retry(flaky, sleep=lambda s: None) == "ok" and len(calls) == 2
    with pytest.raises(ExternalApiError):
        with_retry(lambda: (_ for _ in ()).throw(ExternalApiError("x", "verboten", 403)), sleep=lambda s: None)


# --- Web-Oberfläche / API -------------------------------------------------------------------
H = {"X-BBob": "1"}


def test_ui_and_state(brain):
    c = TestClient(create_app(brain=brain))
    assert "Bürgermeister Bob" in c.get("/").text
    st = c.get("/api/state").json()
    assert st["automation_enabled"] is False and st["publishing_allowed"] is False
    assert c.put("/api/automation", json={"enabled": True}, headers=H).json() == {"automation_enabled": True}


def test_csrf_header_required(brain):
    c = TestClient(create_app(brain=brain))
    assert c.put("/api/automation", json={"enabled": True}).status_code == 403


def test_video_lifecycle_via_api(brain, tmp_path):
    c = TestClient(create_app(brain=brain))
    v = brain.memory.create_video("Laufmaschine")
    brain.memory.update_video(v["id"], status="ready", duration_s=66, qc_json={"passed": True, "checks": []})
    lst = c.get("/api/videos").json()
    assert lst[0]["id"] == v["id"] and lst[0]["has_video"] is False
    assert c.get(f"/api/videos/{v['id']}/file").status_code == 404
    approved = c.post(f"/api/videos/{v['id']}/approve", headers=H).json()
    assert approved["status"] == "approved" and approved["publish_blockers"]
    r = c.post(f"/api/videos/{v['id']}/publish", headers=H)
    assert r.status_code == 409 and "BBOB_ALLOW_PUBLISHING" in r.json()["detail"]
    assert c.post(f"/api/videos/{v['id']}/approve", headers=H).status_code == 409
    assert c.post(f"/api/videos/{v['id']}/reject", json={"reason": "nein"}, headers=H).json()["status"] == "rejected"
    assert c.get("/api/videos/unbekannt").status_code == 404


def test_create_video_reports_errors(brain):
    c = TestClient(create_app(brain=brain))
    assert c.post("/api/videos", json={"topic": "Gibt es nicht"}, headers=H).status_code == 202
    assert "Quellen" in c.get("/api/state").json()["last_production_error"]


def test_token_protection(tmp_path):
    b = BrainAgent(make_settings(tmp_path, app_token="geheim-123"), http_transport=wiki_transport({}))
    c = TestClient(create_app(brain=b))
    assert c.get("/api/state").status_code == 401
    assert c.get("/api/state", headers={"Authorization": "Bearer geheim-123"}).status_code == 200
    assert c.get("/?token=geheim-123").status_code == 200
    assert c.get("/api/state").status_code == 200  # Cookie gesetzt


def test_oauth_callback_rejects_unknown_state(brain):
    c = TestClient(create_app(brain=brain))
    assert c.get("/oauth/tiktok/callback?code=x&state=gefälscht").status_code == 400
    assert c.get("/oauth/tiktok/start", follow_redirects=False).status_code == 409  # nicht eingerichtet


def test_loopback_detection():
    assert is_loopback("127.0.0.1") and is_loopback("localhost") and is_loopback("::1")
    assert not is_loopback("0.0.0.0") and not is_loopback("192.168.1.5")
