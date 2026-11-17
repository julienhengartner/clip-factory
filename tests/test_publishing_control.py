"""Approval-based publishing: five proven stages, user-controlled caption/hashtags/visibility, no automatic
first upload, and no stage is claimed without TikTok's confirmation."""
import pytest
from fastapi.testclient import TestClient

from agents.publishing_stages import current_stage, stages
from app.main import create_app
from brain.orchestrator import BrainAgent
from core.errors import FactoryError
from tests.conftest import make_settings
from tests.fakes import wiki_transport


class ScriptedTikTok:
    """Simulated TikTok API: returns whatever status the test scripts; nothing leaves the machine."""

    def __init__(self, statuses, public_ids=()):
        self.statuses, self.public_ids, self.uploads = list(statuses), list(public_ids), []

    def missing_requirements(self):
        return []

    @property
    def connected(self):
        return True

    def creator_info(self):
        return {"privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"]}

    def init_upload(self, path, mode, title="", privacy_level="SELF_ONLY"):
        self.uploads.append({"title": title, "privacy": privacy_level, "mode": mode})
        return {"publish_id": f"p{len(self.uploads)}", "upload_url": "https://upload.example"}

    def upload_file(self, url, path):
        pass

    def fetch_status(self, publish_id):
        status = self.statuses.pop(0) if self.statuses else "PROCESSING_UPLOAD"
        return {"status": status, "publicaly_available_post_id": [777] if status == "PUBLISH_COMPLETE" else []}

    def list_videos(self):
        return [{"id": i} for i in self.public_ids]


def validated_video(brain, tmp_path):
    video = tmp_path / "pilot.mp4"
    video.write_bytes(b"x" * 100)
    v = brain.memory.create_video("THE MAYOR BANS MONDAYS!", category="bobbington")
    return brain.memory.update_video(v["id"], status="ready", video_path=str(video), duration_s=74.5,
                                     qc_json={"passed": True, "checks": []}, title="THE MAYOR BANS MONDAYS!")


@pytest.fixture
def brain(tmp_path, monkeypatch):
    b = BrainAgent(make_settings(tmp_path, allow_publishing=True, tiktok_publish_mode="direct"),
                   http_transport=wiki_transport({}))
    # length check reads the real file – our stand-in file is not a video
    monkeypatch.setattr("agents.tiktok_publisher.probe_duration", lambda *a, **k: 74.5)
    return b


def stage_keys(brain, vid):
    v = brain.memory.get_video(vid)
    return [s["key"] for s in stages(v, brain.memory.publications(vid)) if s["done"]]


def test_five_stages_are_only_reached_with_proof(brain, tmp_path):
    v = validated_video(brain, tmp_path)
    assert stage_keys(brain, v["id"]) == ["generated", "validated"]
    brain.approve(v["id"])
    assert stage_keys(brain, v["id"]) == ["generated", "validated", "approved"]

    tiktok = ScriptedTikTok(["PROCESSING_UPLOAD", "PUBLISH_COMPLETE"])
    brain.publisher.client = tiktok
    with pytest.raises(FactoryError, match="nicht von dir bestätigt"):
        brain.publish(v["id"])                                     # no upload without the user's caption
    brain.set_publishing_details(v["id"], "The Mayor bans Mondays. What could go wrong?", "#bobbington #comedy",
                                 "SELF_ONLY")
    out = brain.publish(v["id"])
    assert "bestätigt den Upload" in out.message
    assert tiktok.uploads[0]["title"].startswith("The Mayor bans Mondays.") and "#bobbington" in tiktok.uploads[0]["title"]
    assert tiktok.uploads[0]["privacy"] == "SELF_ONLY"
    assert "uploaded" not in stage_keys(brain, v["id"])            # our HTTP request is not a confirmation
    brain.publisher.refresh()                                      # TikTok: still processing
    assert "uploaded" not in stage_keys(brain, v["id"])
    brain.publisher.refresh()                                      # TikTok: PUBLISH_COMPLETE, but private
    assert stage_keys(brain, v["id"])[-1] == "uploaded"
    assert brain.memory.get_video(v["id"])["status"] == "uploaded"  # never 'published' while private


def test_public_publication_requires_public_visibility(brain, tmp_path):
    v = validated_video(brain, tmp_path)
    brain.approve(v["id"])
    brain.set_publishing_details(v["id"], "Pilot", "", "PUBLIC_TO_EVERYONE")
    brain.publisher.client = ScriptedTikTok(["PUBLISH_COMPLETE"])
    brain.publish(v["id"])
    brain.publisher.refresh()
    assert current_stage(brain.memory.get_video(v["id"]), brain.memory.publications(v["id"])) == "published"
    assert brain.memory.get_video(v["id"])["status"] == "published"


def test_inbox_mode_public_only_if_tiktok_lists_the_post(tmp_path, monkeypatch):
    b = BrainAgent(make_settings(tmp_path, allow_publishing=True, tiktok_publish_mode="inbox"),
                   http_transport=wiki_transport({}))
    monkeypatch.setattr("agents.tiktok_publisher.probe_duration", lambda *a, **k: 74.5)
    v = validated_video(b, tmp_path)
    b.approve(v["id"])
    b.set_publishing_details(v["id"], "Pilot", "#bobbington", None)   # visibility chosen in the TikTok app
    b.publisher.client = ScriptedTikTok(["SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "PUBLISH_COMPLETE"])
    b.publish(v["id"])
    b.publisher.refresh()
    assert stage_keys(b, v["id"])[-1] == "uploaded"                  # draft in the inbox, confirmed
    b.publisher.refresh()                                            # posted, but not in the public list
    assert b.memory.get_video(v["id"])["status"] == "uploaded"
    b.publisher.client.public_ids = [777]
    b.publisher.refresh()
    assert b.memory.get_video(v["id"])["status"] == "published"


def test_failed_upload_keeps_video_approved(brain, tmp_path):
    v = validated_video(brain, tmp_path)
    brain.approve(v["id"])
    brain.set_publishing_details(v["id"], "Pilot", "", "SELF_ONLY")
    brain.publisher.client = ScriptedTikTok(["FAILED"])
    brain.publish(v["id"])
    brain.publisher.refresh()
    assert brain.memory.get_video(v["id"])["status"] == "approved"
    assert "uploaded" not in stage_keys(brain, v["id"])


def test_no_automatic_first_upload(brain, tmp_path):
    v = validated_video(brain, tmp_path)
    brain.approve(v["id"])
    brain.set_publishing_details(v["id"], "Pilot", "", "SELF_ONLY")
    brain.publisher.client = ScriptedTikTok(["PUBLISH_COMPLETE"])
    assert brain.publish_due() == []                                 # automation never uploads by itself
    with pytest.raises(FactoryError, match="manueller Upload"):
        brain.set_auto_publish(True)
    brain.publish(v["id"])                                           # the user's manual first upload
    brain.publisher.refresh()
    brain.set_auto_publish(True)                                     # only now may automation be enabled
    assert brain.auto_publish_allowed() == (True, "ok")
    brain.set_auto_publish(False)
    assert brain.auto_publish_allowed()[0] is False


def test_publishing_details_validation(brain, tmp_path):
    v = validated_video(brain, tmp_path)
    with pytest.raises(FactoryError):
        brain.set_publishing_details(v["id"], "x", "", "EVERYONE_PLEASE")
    with pytest.raises(FactoryError):
        brain.set_publishing_details(v["id"], "   ", "", "SELF_ONLY")


def test_api_publishing_endpoints(brain, tmp_path):
    v = validated_video(brain, tmp_path)
    c = TestClient(create_app(brain=brain))
    H = {"X-BBob": "1"}
    detail = c.get(f"/api/videos/{v['id']}").json()
    assert [s["key"] for s in detail["stages"]] == ["generated", "validated", "approved", "uploaded", "published"]
    assert "SELF_ONLY" in detail["privacy_options"]
    assert c.put(f"/api/videos/{v['id']}/publishing", json={"caption": "x", "privacy_level": "NOPE"}, headers=H).status_code == 422
    ok = c.put(f"/api/videos/{v['id']}/publishing", json={"caption": "Mondays!", "hashtags": "#bobbington",
                                                          "privacy_level": "SELF_ONLY"}, headers=H).json()
    assert ok["caption"] == "Mondays!" and ok["caption_confirmed_at"]
    st = c.get("/api/state").json()["auto_publish"]
    assert st["enabled"] is False and st["effective"] is False
    assert c.put("/api/auto-publish", json={"enabled": True}, headers=H).status_code == 409
