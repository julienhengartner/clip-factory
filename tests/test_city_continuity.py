"""Persistent city continuity: state, story events, versions, validation – and a real Blender round trip."""
import copy
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from bobbington import bible
from bobbington.city_seed import seed_state
from bobbington.citystate import (CityChange, CityStore, apply_changes, character_designs, check_scene_inventory,
                                  check_state_continuity, compare_reference_images, version_name)
from bobbington.episode import Episode, load_episode
from bobbington.generator import PREMISES, build_episode
from config import Settings
from storage.database import Database

ROOT = Path(__file__).resolve().parent.parent
PILOT = ROOT / "episodes" / "pilot_mayor_bans_mondays.json"
BLENDER = Settings(_env_file=None).blender_bin


def base_state():
    st = seed_state()
    st["characters"] = {"designs": character_designs(), "last_positions": {}}
    return st


PLAQUE = CityChange(op="add", group="mayors_office/test_plaque", template="plaque",
                    params={"at": [0.5, 0.2, 1.0], "text": "TEST"}, reason="test", from_shot="x")


# --- state & story events --------------------------------------------------------------------------
def test_seed_is_complete_and_stable():
    a, b = seed_state(), seed_state()
    assert a == b                                              # deterministic: same town every time
    ids = [o["id"] for o in a["objects"]]
    assert len(ids) == len(set(ids)) == 237
    assert {o["location"] for o in a["objects"]} == {"mayors_office", "council_chamber", "main_street", "pub", "title_card"}
    assert set(a["marks"]) == set(a["ref_cameras"])
    houses = {o["group"] for o in a["objects"] if o["category"] == "building"}
    assert len(houses) == 6


def test_apply_all_operations():
    st = base_state()
    changes = [PLAQUE,
               CityChange(op="remove", group="main_street/historic_puddle", reason="evaporated"),
               CityChange(op="set_text", object_id="pub/chalkboard/chalk_text#0", text="CLOSED", reason="r"),
               CityChange(op="set_condition", group="main_street/house_2", condition="damaged", reason="storm"),
               CityChange(op="move", group="main_street/bin_0", delta=[0.5, 0, 0], reason="moved by Nigel"),
               CityChange(op="set_environment", key="weather", value="rain", reason="rain")]
    new, rec = apply_changes(st, changes)
    objs = {o["id"]: o for o in new["objects"]}
    assert "mayors_office/test_plaque/plaque#0" in objs
    assert not any(o["group"] == "main_street/historic_puddle" for o in new["objects"])
    assert {o["group"] for o in new["removed"]} == {"main_street/historic_puddle"}     # history kept
    assert objs["pub/chalkboard/chalk_text#0"]["body"] == "CLOSED" and rec[2]["before"].startswith("TODAY")
    assert all(o["condition"] == "damaged" for o in new["objects"] if o["group"] == "main_street/house_2")
    assert new["environment"]["weather"] == "rain"
    assert st == base_state()                                  # the parent state is never modified
    assert check_state_continuity(st, new, rec) == []


@pytest.mark.parametrize("change", [
    CityChange(op="add", group="mayors_office/desk", template="plaque", reason="dup"),
    CityChange(op="remove", group="main_street/unicorn", reason="x"),
    CityChange(op="set_text", object_id="pub/bar/bar#0", text="x", reason="not a text"),
    CityChange(op="set_condition", group="main_street/house_0", condition="exploded", reason="x"),
    CityChange(op="teleport", group="main_street/house_0", reason="x")])
def test_invalid_events_are_refused(change):
    with pytest.raises(ValueError):
        apply_changes(base_state(), [change])


def test_undeclared_changes_are_detected(monkeypatch):
    st = base_state()
    new, rec = apply_changes(st, [PLAQUE])
    tampered = copy.deepcopy(new)
    house = next(o for o in tampered["objects"] if o["group"] == "main_street/house_1")
    house["loc"][0] += 0.3                                    # someone "redesigned" a house
    tampered["objects"] = [o for o in tampered["objects"] if o["group"] != "main_street/lamp_0"]
    tampered["marks"]["pub"]["behind_bar"][0] += 1
    checks = {i["check"] for i in check_state_continuity(st, tampered, rec)}
    assert {"undeclared_change", "marks_changed"} <= checks
    # a character's look changes in the bible without a declared redesign
    monkeypatch.setitem(bible.CAST["winston"]["look"], "height", 1.9)
    import bobbington.citystate as cs
    monkeypatch.setattr(cs, "CAST", bible.CAST)
    assert any(i["check"] == "bible_differs_from_state" for i in check_state_continuity(st, new, rec))


def test_scene_inventory_check():
    st = base_state()
    inv = {"objects": {o["id"]: {"loc": o["loc"], "material": (o["material"]["name"] if o.get("material") else
                                                               f"text_{o['colour']}" if o["kind"] == "text" else ""),
                                 **({"body": o["body"]} if o["kind"] == "text" else {})} for o in st["objects"]}}
    assert check_scene_inventory(st, inv) == []
    broken = copy.deepcopy(inv)
    broken["objects"].pop("main_street/house_0/house#0")
    broken["objects"]["pub/chalkboard/chalk_text#0"]["body"] = "WRONG"
    broken["objects"]["mayors_office/desk/desk#0"]["loc"][1] += 1
    broken["objects"]["stray/object#0"] = {"loc": [0, 0, 0]}
    checks = {i["check"] for i in check_scene_inventory(st, broken)}
    assert checks == {"missing_in_scene", "text_mismatch", "position_mismatch", "unexpected_in_scene"}


def test_reference_image_comparison(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    img = np.full((40, 30, 3), 120, np.uint8)
    for loc in ("pub", "main_street"):
        Image.fromarray(img).save(a / f"{loc}.png")
        Image.fromarray(img).save(b / f"{loc}.png")
    assert compare_reference_images(a, b, set()) == []
    changed = img.copy()
    changed[:, :10] = 255
    Image.fromarray(changed).save(b / "main_street.png")
    assert compare_reference_images(a, b, set())[0]["check"] == "visual_change_without_story_event"
    assert compare_reference_images(a, b, {"main_street"}) == []      # declared story event


# --- versions --------------------------------------------------------------------------------------
@pytest.fixture
def store(tmp_path):
    return CityStore(Database(tmp_path / "db.sqlite"), tmp_path / "city")


def fake_build(store, n):
    f = store.folder(n)
    (f / "scene.blend").write_bytes(b"blend")
    (f / "inventory.json").write_text("{}", encoding="utf-8")
    store.record_continuity(n, [])


def test_version_lifecycle_and_immutability(store):
    store.create_baseline()
    with pytest.raises(ValueError):
        store.approve(1)                                      # continuity not yet checked
    fake_build(store, 1)
    store.approve(1)
    assert store.latest_approved() == 1 and version_name(1) == "Bobbington_City_v001"
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("UPDATE city_versions SET note='x' WHERE number=1")      # approved = immutable
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("DELETE FROM city_versions WHERE number=1")              # never deleted
    n, state, rec = store.create_draft(1, [PLAQUE], "s01e01", {"winston": {"location": "mayors_office"}})
    assert n == 2 and state["characters"]["last_positions"]["winston"]["location"] == "mayors_office"
    with pytest.raises(ValueError):
        store.create_draft(2, [], "s01e02")                   # drafts never start from unapproved versions
    fake_build(store, 2)
    store.approve(2)
    assert store.latest_approved() == 2
    with pytest.raises(FileExistsError):
        store._write(2, state, [], 1, "x")                    # version folders are never overwritten


def test_stale_draft_cannot_become_baseline(store):
    store.create_baseline()
    fake_build(store, 1)
    store.approve(1)
    a, _, _ = store.create_draft(1, [PLAQUE], "s01e01")
    b, _, _ = store.create_draft(1, [CityChange(op="remove", group="main_street/historic_puddle", reason="r")], "s01e02")
    fake_build(store, a), fake_build(store, b)
    store.approve(a)
    with pytest.raises(ValueError, match="re-render"):
        store.approve(b)                                      # built on v001, but v002 is now the town


def test_restore_creates_new_version(store):
    store.create_baseline()
    fake_build(store, 1)
    store.approve(1)
    n, _, _ = store.create_draft(1, [PLAQUE], "s01e01")
    fake_build(store, n)
    store.approve(n)
    r = store.restore(1, "plaque was a mistake")
    assert r == 3 and store.load_state(3)["objects"] == store.load_state(1)["objects"]
    assert store.row(1)["status"] == "approved" and store.row(2)["status"] == "approved"   # history intact
    store.approve(3)
    assert store.latest_approved() == 3


# --- episodes ----------------------------------------------------------------------------------------
def test_episode_city_changes_are_validated():
    data = json.loads(PILOT.read_text(encoding="utf-8"))
    data["city_changes"][0]["from_shot"] = "no_such_shot"
    with pytest.raises(ValueError, match="unknown shot"):
        Episode.model_validate(data)
    data["city_changes"][0]["from_shot"] = "punchline"
    data["city_changes"][0]["reason"] = ""
    with pytest.raises(ValueError, match="reason"):
        Episode.model_validate(data)


def test_episodes_chain_on_one_town():
    """Pilot + all generated episodes applied in sequence: every change persists, nothing else moves."""
    st = base_state()
    for ep in [load_episode(PILOT)] + [build_episode(p, i) for i, p in enumerate(PREMISES, 2)]:
        new, rec = apply_changes(st, [CityChange(**c) for c in ep.city_changes])
        assert check_state_continuity(st, new, rec) == []
        st = new
    ids = {o["id"] for o in st["objects"]}
    assert "mayors_office/mondays_plaque/plaque#0" in ids                  # pilot's plaque is still there
    assert not any(o["group"] == "main_street/historic_puddle" for o in st["objects"])   # puddle stays gone
    assert "main_street/roundabout_works/site_sign#0" in ids


# --- real Blender round trip ---------------------------------------------------------------------------
@pytest.mark.skipif(not Path(BLENDER).is_file(), reason="Blender not installed")
def test_blender_baseline_derive_and_persistence(tmp_path):
    from bobbington.continuity import CityManager, ContinuityError
    from tests.conftest import make_settings
    s = make_settings(tmp_path)
    m = CityManager(s, Database(s.db_path))
    assert m.ensure_baseline() == 1
    pilot = load_episode(PILOT)
    info = m.prepare(pilot)                                    # opens v001's scene.blend, adds plaque + chalk text
    assert info["draft_version"] == "Bobbington_City_v002"
    assert m.prepare(pilot)["reused"] is True                  # same episode on same baseline -> same draft
    v1, v2 = m.store.folder(1), m.store.folder(2)
    for loc in ("council_chamber", "main_street", "title_card"):
        a = np.asarray(Image.open(v1 / "refs" / f"{loc}.png"), dtype=float)
        b = np.asarray(Image.open(v2 / "refs" / f"{loc}.png"), dtype=float)
        assert np.abs(a - b).mean() < 0.05, loc                 # untouched locations identical
    m.approve(2)
    # next episode: does NOT mention the plaque – it must still be in the town
    roundabout = build_episode(next(p for p in PREMISES if p["id"] == "roundabout"), 3)
    info3 = m.prepare(roundabout)
    inv3 = json.loads((m.store.folder(3) / "inventory.json").read_text(encoding="utf-8"))["objects"]
    assert "mayors_office/mondays_plaque/plaque#0" in inv3
    assert inv3["pub/chalkboard/chalk_text#0"]["body"] == roundabout.city_changes[0]["text"]
    assert "main_street/roundabout_works/fence#0" in inv3
    assert info3["base_version"] == "Bobbington_City_v002"
    # an episode that contradicts the town (removing a puddle twice) is refused
    bad = build_episode(next(p for p in PREMISES if p["id"] == "rain"), 2)
    m.approve(3)
    m.prepare(bad)
    m.approve(4)
    with pytest.raises((ValueError, ContinuityError)):
        m.prepare(bad.model_copy(update={"id": "s01e09"}))
