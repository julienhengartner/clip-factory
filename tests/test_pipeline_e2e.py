"""Ende-zu-Ende: echte Windows-Stimme + echtes FFmpeg, Recherche über simulierte Wikipedia-Antworten."""
from pathlib import Path

import pytest

from brain.orchestrator import BrainAgent
from core.errors import FactoryError
from storage.models import VideoStatus
from tests.conftest import make_settings, requires_windows_tts
from tests.fakes import LONG_TEXT, SHORT_TEXT, wiki_transport
from tests.test_agents import FakeTikTok
from video_engine.ffmpeg import probe, probe_duration


@pytest.fixture
def brain_factory(tmp_path):
    def make(articles, **overrides):
        s = make_settings(tmp_path, **overrides)
        return BrainAgent(s, http_transport=wiki_transport(articles))
    return make


@requires_windows_tts
def test_full_production_publish_cycle(brain_factory):
    brain = brain_factory({"Laufmaschine": LONG_TEXT}, allow_publishing=True)
    video = brain.produce(topic="Laufmaschine")
    assert video["status"] == "ready", (video["error"], video["qc"])

    # Länge: unabhängig per ffprobe nachgemessen
    path = Path(video["video_path"])
    duration = probe_duration(path)
    assert 60.0 <= duration <= 80.0
    info = probe(path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert (v["codec_name"], v["width"], v["height"], a["codec_name"]) == ("h264", 360, 640, "aac")

    # Archiv vollständig, Zwischendateien entfernt
    folder = path.parent
    for name in ("video.mp4", "thumbnail.jpg", "subtitles.srt", "subtitles.ass", "script.json", "qc.json", "sources.txt"):
        assert (folder / name).is_file(), name
    assert not (folder / "work").exists()

    # Gedächtnis: Hook-Kandidaten, Sprechrate gelernt, Schritte protokolliert
    assert brain.db.scalar("SELECT COUNT(*) FROM hooks WHERE video_id=?", (video["id"],)) >= 3
    assert brain.memory.insights("speech_rate")
    steps = {e["message"][:4] for e in brain.memory.events(video_id=video["id"])}
    assert {"[01]", "[05]", "[06]", "[10]", "[15]", "[19]", "[20]"} <= steps

    # Ohne Freigabe keine Veröffentlichung
    brain.publisher.client = FakeTikTok()
    with pytest.raises(FactoryError):
        brain.publish(video["id"])
    brain.approve(video["id"])
    with pytest.raises(FactoryError):
        brain.publish(video["id"])                      # caption/visibility not confirmed by the user yet
    brain.set_publishing_details(video["id"], "Die Laufmaschine", "#test", None)
    outcome = brain.publish(video["id"])
    assert outcome.status == "processing" and brain.publisher.client.uploaded
    assert brain.memory.get_video(video["id"])["status"] == VideoStatus.PUBLISHING.value
    # "veröffentlicht" erst nach bestätigter API-Antwort
    brain.publisher.refresh()
    final = brain.memory.get_video(video["id"])
    assert final["status"] == "published" and final["published_at"]
    assert brain.memory.publications(video["id"])[0]["external_id"] == "123"


@requires_windows_tts
def test_too_little_material_is_rejected_not_padded(brain_factory):
    brain = brain_factory({"Testweiler": SHORT_TEXT})
    video = brain.produce(topic="Testweiler")
    assert video["status"] == "failed"
    assert "Material" in video["error"] or "Sekunden" in video["error"]
    assert video["video_path"] is None  # kein zu kurzes Video erzeugt


def test_unverifiable_topic_raises(brain_factory):
    brain = brain_factory({})
    with pytest.raises(FactoryError):
        brain.produce(topic="Gibt es nicht")


def test_approve_requires_ready(brain_factory):
    brain = brain_factory({})
    v = brain.memory.create_video("x")
    with pytest.raises(FactoryError):
        brain.approve(v["id"])
    brain.memory.update_video(v["id"], status="qc_failed")
    with pytest.raises(FactoryError):
        brain.approve(v["id"])  # QC-Fehler können nie freigegeben werden
    assert brain.reject(v["id"], "schlecht")["status"] == "rejected"


def test_only_one_production_at_a_time(brain_factory):
    brain = brain_factory({})
    brain._lock.acquire()
    try:
        with pytest.raises(FactoryError):
            brain.produce(topic="x")
    finally:
        brain._lock.release()


def test_interrupted_productions_are_recovered(brain_factory):
    brain = brain_factory({})
    v = brain.memory.create_video("Abgestürzt")
    brain.db.execute("UPDATE videos SET updated_at='2020-01-01T00:00:00+00:00' WHERE id=?", (v["id"],))
    fresh = brain.memory.create_video("Läuft gerade")
    assert brain.recover_interrupted() == 1
    assert brain.memory.get_video(v["id"])["status"] == "failed"
    assert brain.memory.get_video(fresh["id"])["status"] == "producing"
