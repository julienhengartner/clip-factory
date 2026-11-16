import sqlite3

import pytest

from brain.budget import BudgetGuard
from brain.memory import Memory
from core.errors import BudgetExceededError, PaidApiNotAllowedError, PublishingNotAllowedError
from storage.database import MIGRATIONS, Database
from storage.models import Idea, ResearchItem, VideoStatus
from tests.conftest import make_settings


def test_schema_version_and_idempotent_migration(settings):
    db = Database(settings.db_path)
    assert db.schema_version == len(MIGRATIONS)
    assert Database(settings.db_path).schema_version == len(MIGRATIONS)  # zweites Öffnen migriert nicht erneut


def test_research_dedupe_by_url(memory):
    item = ResearchItem(title="A", summary="x", url="https://de.wikipedia.org/wiki/A", source="wikipedia")
    first = memory.add_research(item)
    second = memory.add_research(item.model_copy(update={"summary": "neu", "verified": True}))
    assert first == second
    got = memory.get_research([first])[0]
    assert got.summary == "neu" and got.verified is True


def test_ideas_and_videos_persist(settings, memory):
    idea_id = memory.add_idea(Idea(title="Laufmaschine", angle="Erfindung", research_ids=[1, 2], score=0.7))
    video = memory.create_video("Laufmaschine", idea_id=idea_id)
    memory.update_video(video["id"], status=VideoStatus.READY, duration_s=66.2, script_json={"a": 1})
    again = Memory(Database(settings.db_path)).get_video(video["id"])
    assert again["status"] == "ready" and again["duration_s"] == 66.2 and again["script"] == {"a": 1}
    assert memory.get_idea(idea_id).research_ids == [1, 2]
    assert memory.videos_created_today() == 1
    with pytest.raises(ValueError):
        memory.update_video(video["id"], evil="x")
    with pytest.raises(KeyError):
        memory.update_video("unknown", status="ready")


def test_comment_author_is_hashed(memory, db):
    assert memory.upsert_comment("instagram", "c1", "Tolles Video!", "m1", "max.muster", 3, None) is True
    assert memory.upsert_comment("instagram", "c1", "Tolles Video!", "m1", "max.muster", 5, None) is False
    row = db.query_one("SELECT * FROM comments")
    assert row["author_hash"] and "max" not in row["author_hash"] and row["like_count"] == 5


def test_insights_settings_runs(memory):
    memory.set_insight("topic_category", "geschichte", {"mean": 1.2, "n": 3}, 0.5)
    memory.set_insight("topic_category", "geschichte", {"mean": 1.4, "n": 4}, 0.6)
    assert memory.get_insight("topic_category", "geschichte")["n"] == 4
    assert memory.get_setting("automation_enabled", False) is False
    memory.set_setting("automation_enabled", True)
    assert memory.get_setting("automation_enabled") is True
    run = memory.start_run("daily")
    memory.finish_run(run, "ok", {"videos": 1})
    assert memory.runs()[0]["status"] == "ok"


def test_latest_performance(memory):
    memory.add_performance("tiktok", "v1", views=10, likes=1)
    memory.add_performance("tiktok", "v1", views=50, likes=4)
    memory.add_performance("tiktok", "v2", views=5)
    latest = {r["external_id"]: r for r in memory.latest_performance("tiktok")}
    assert latest["v1"]["views"] == 50 and len(latest) == 2


def test_backup_is_consistent_and_rotates(settings, memory, db):
    memory.log("info", "test", "hallo")
    for _ in range(4):
        path = db.backup(settings.backups_dir, keep=2)
    assert len(list(settings.backups_dir.glob("brain-*.db"))) == 2
    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    con.close()


def test_budget_guard(tmp_path, memory):
    blocked = BudgetGuard(make_settings(tmp_path), memory)
    with pytest.raises(PaidApiNotAllowedError):
        blocked.authorize_paid_call("openai", "image")
    with pytest.raises(PublishingNotAllowedError):
        blocked.require_publishing_allowed("tiktok")
    allowed = BudgetGuard(make_settings(tmp_path, allow_paid_apis=True, max_paid_calls_per_day=2), memory)
    allowed.authorize_paid_call("openai", "image")
    allowed.authorize_paid_call("openai", "image")
    with pytest.raises(BudgetExceededError):
        allowed.authorize_paid_call("openai", "image")
    assert memory.paid_calls_today() == 2


def test_oauth_state_single_use(memory):
    memory.add_oauth_state("abc", "tiktok")
    assert memory.consume_oauth_state("abc", "tiktok") is True
    assert memory.consume_oauth_state("abc", "tiktok") is False
