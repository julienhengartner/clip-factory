"""Persistent, versioned city state of Bobbington.

Bobbington is ONE persistent place. The city state (every object with ID, transform, dimensions, material,
text, condition + environment, marks, reference cameras, character designs/locations) is stored in
versions Bobbington_City_v001, v002, … Each version folder holds:

    state.json        structured city data (source of truth)
    scene.blend       the Blender scene of exactly this state (reused by the next episode)
    refs/<loc>.png    reference renders from fixed cameras
    inventory.json    what is actually in scene.blend (checked against state.json)
    changes.json      explicit story events relative to the parent version
    manifest.json     version, parent, episode, hashes, continuity result

Rules enforced here and in the database (triggers): approved/rejected versions are immutable and never
deleted; a new episode always starts from the latest APPROVED version; the city changes only through
declared story events; an episode's draft version becomes the new baseline only after approval, and only if
it was built on the current baseline.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from bobbington.bible import CAST
from bobbington.city_seed import Recorder, mat, seed_state
from storage.database import Database, utcnow

PREFIX = "Bobbington_City_v"
CONDITIONS = {"intact", "damaged", "under_construction", "closed"}


def version_name(n: int) -> str:
    return f"{PREFIX}{n:03d}"


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def state_hash(state: dict) -> str:
    return hashlib.sha256(canonical(state).encode()).hexdigest()


def character_designs() -> dict[str, str]:
    """Hash of every character's visual spec – a change here is a design change and must be declared."""
    return {cid: hashlib.sha256(canonical(c["look"]).encode()).hexdigest()[:16] for cid, c in CAST.items()}


# --- story events ------------------------------------------------------------------------------------
class CityChange(BaseModel):
    """One explicit, traceable change of the town. `from_shot` = first shot of the episode showing it."""
    op: str                                  # add | remove | set_text | set_condition | move | set_environment | redesign_character
    location: str | None = None
    group: str | None = None                 # e.g. 'mayors_office/mondays_plaque'
    template: str | None = None              # for 'add'
    params: dict = Field(default_factory=dict)
    object_id: str | None = None             # for 'set_text'
    text: str | None = None
    condition: str | None = None
    delta: list[float] | None = None
    key: str | None = None
    value: object = None
    character: str | None = None
    reason: str = ""
    from_shot: str | None = None


def _template_objects(location: str, group: str, template: str, p: dict) -> list[dict]:
    """Reusable assets for story events. Positions are absolute world coordinates."""
    k = Recorder()
    k.location = location
    g = group.split("/", 1)[1]
    x, y, z = p.get("at", [0.0, 0.0, 0.0])
    if template == "plaque":
        with k.group(g, "sign"):
            k.cube("plaque", (x, y, z), (0.7, 0.05, 0.32), mat("brass", "gold", 0.25, 1.0))
            k.text("plaque_text", p.get("text", "HISTORIC"), (x, y - 0.03, z), size=p.get("size", 0.045),
                   colour="burgundy_dark")
    elif template == "statue":
        with k.group(g, "landmark"):
            k.cube("plinth", (x, y, z + 0.5), (0.8, 0.8, 1.0), mat("stone", "stone", 0.6))
            k.sphere("statue_body", (x, y, z + 1.45), (0.3, 0.25, 0.45), mat("bronze", "#8C6A3A", 0.35, 0.8))
            k.sphere("statue_head", (x, y, z + 2.05), (0.2, 0.2, 0.22), mat("bronze", "#8C6A3A", 0.35, 0.8))
            k.text("statue_label", p.get("text", "OUR GLORIOUS MAYOR"), (x, y - 0.42, z + 0.6), size=0.06, colour="gold")
    elif template == "construction_site":
        w = p.get("width", 3.0)
        with k.group(g, "construction"):
            for i in range(int(w / 0.6) + 1):
                k.cube("fence", (x - w / 2 + i * 0.6, y, z + 0.5), (0.55, 0.04, 1.0), mat("fence", "#E8742C", 0.6))
            for i in range(3):
                k.cone("cone", (x - 0.8 + i * 0.8, y - 0.5, z + 0.18), 0.12, 0.02, 0.36, mat("cone", "#E8742C", 0.5))
            k.cube("site_sign", (x, y - 0.05, z + 1.2), (1.4, 0.05, 0.4), mat("cream_board", "cream", 0.6))
            k.text("site_label", p.get("text", "WORKS IN PROGRESS"), (x, y - 0.09, z + 1.2), size=0.07, colour="ink")
    elif template == "road_closure":
        with k.group(g, "street"):
            k.cube("barrier", (x, y, z + 0.5), (p.get("width", 4.0), 0.12, 0.15), mat("barrier_red", "burgundy", 0.5))
            for s in (-1, 1):
                k.cylinder("barrier_leg", (x + s * p.get("width", 4.0) / 2.2, y, z + 0.25), 0.04, 0.5, mat("ink", "ink", 0.3))
            k.text("closure_label", p.get("text", "ROAD CLOSED"), (x, y - 0.08, z + 0.5), size=0.09, colour="cream")
    elif template == "bench":
        with k.group(g, "street_furniture"):
            k.cube("bench_seat", (x, y, z + 0.45), (1.6, 0.45, 0.08), mat("bench_wood", "#6B3F22", 0.5))
            k.cube("bench_back", (x, y + 0.2, z + 0.75), (1.6, 0.06, 0.5), mat("bench_wood", "#6B3F22", 0.5))
            if p.get("text"):
                k.text("bench_plaque", p["text"], (x, y + 0.16, z + 0.75), size=0.05, colour="gold")
    elif template == "tree":
        with k.group(g, "vegetation"):
            k.cylinder("trunk", (x, y, z + 0.8), 0.12, 1.6, mat("bark", "#5A3A26", 0.9))
            k.sphere("crown", (x, y, z + 2.1), (0.9, 0.9, 1.0), mat("leaves", "racing_green", 0.8))
    else:
        raise ValueError(f"unknown template '{template}'")
    return k.objects


def apply_changes(state: dict, changes: list[CityChange]) -> tuple[dict, list[dict]]:
    """Returns (new_state, change_records). Every record explains exactly which objects changed."""
    new = copy.deepcopy(state)
    objs = new["objects"]
    records = []
    for ch in changes:
        rec = {"op": ch.op, "group": ch.group, "reason": ch.reason, "from_shot": ch.from_shot, "objects": []}
        if ch.op == "add":
            if any(o["group"] == ch.group for o in objs):
                raise ValueError(f"group {ch.group} already exists")
            added = _template_objects(ch.location or ch.group.split("/")[0], ch.group, ch.template, ch.params)
            for o in added:
                o["added_by"] = ch.reason or "story event"
            objs.extend(added)
            rec["objects"] = [o["id"] for o in added]
            rec["template"] = ch.template
        elif ch.op == "remove":
            hit = [o for o in objs if o["group"] == ch.group]
            if not hit:
                raise ValueError(f"group {ch.group} does not exist")
            new.setdefault("removed", []).extend({**o, "removed_because": ch.reason} for o in hit)
            new["objects"] = objs = [o for o in objs if o["group"] != ch.group]
            rec["objects"] = [o["id"] for o in hit]
        elif ch.op == "set_text":
            o = next((o for o in objs if o["id"] == ch.object_id), None)
            if not o or o["kind"] != "text":
                raise ValueError(f"text object {ch.object_id} not found")
            rec["before"], o["body"] = o["body"], ch.text
            rec["objects"] = [o["id"]]
        elif ch.op == "set_condition":
            if ch.condition not in CONDITIONS:
                raise ValueError(f"unknown condition {ch.condition}")
            hit = [o for o in objs if o["group"] == ch.group]
            if not hit:
                raise ValueError(f"group {ch.group} does not exist")
            for o in hit:
                o["condition"] = ch.condition
            rec["objects"] = [o["id"] for o in hit]
            rec["condition"] = ch.condition
        elif ch.op == "move":
            hit = [o for o in objs if o["group"] == ch.group]
            if not hit or not ch.delta:
                raise ValueError(f"cannot move {ch.group}")
            for o in hit:
                o["loc"] = [round(a + b, 5) for a, b in zip(o["loc"], ch.delta)]
                if o["kind"] == "light":
                    o["target"] = [round(a + b, 5) for a, b in zip(o["target"], ch.delta)]
            rec["objects"] = [o["id"] for o in hit]
            rec["delta"] = ch.delta
        elif ch.op == "set_environment":
            rec["key"] = ch.key
            rec["before"] = new["environment"].get(ch.key)
            new["environment"][ch.key] = ch.value
        elif ch.op == "redesign_character":
            new["characters"]["designs"][ch.character] = character_designs()[ch.character]
            rec["character"] = ch.character
        else:
            raise ValueError(f"unknown op {ch.op}")
        records.append(rec)
    return new, records


# --- continuity ---------------------------------------------------------------------------------------
def diff_states(old: dict, new: dict) -> dict:
    a = {o["id"]: o for o in old["objects"]}
    b = {o["id"]: o for o in new["objects"]}
    changed = sorted(i for i in a.keys() & b.keys() if canonical(a[i]) != canonical(b[i]))
    env = sorted(k for k in set(old["environment"]) | set(new["environment"])
                 if old["environment"].get(k) != new["environment"].get(k))
    return {"added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys()), "changed": changed,
            "environment": env, "marks_changed": old.get("marks") != new.get("marks"),
            "ref_cameras_changed": old.get("ref_cameras") != new.get("ref_cameras"),
            "designs_changed": sorted(c for c in old["characters"]["designs"]
                                      if old["characters"]["designs"][c] != new["characters"]["designs"].get(c))}


def check_state_continuity(parent: dict, draft: dict, records: list[dict]) -> list[dict]:
    """Every difference between parent and draft must be explained by a declared story event."""
    d = diff_states(parent, draft)
    declared = {i for r in records for i in r["objects"]}
    env_keys = {r["key"] for r in records if r["op"] == "set_environment"}
    issues = []
    for kind in ("added", "removed", "changed"):
        for oid in d[kind]:
            if oid not in declared:
                issues.append({"check": "undeclared_change", "detail": f"{kind}: {oid}"})
    for key in d["environment"]:
        if key not in env_keys:
            issues.append({"check": "undeclared_environment_change", "detail": key})
    if d["marks_changed"]:
        issues.append({"check": "marks_changed", "detail": "character marks may only change with a declared event"})
    if d["ref_cameras_changed"]:
        issues.append({"check": "reference_cameras_changed", "detail": "reference cameras must stay fixed"})
    redesigned = {r.get("character") for r in records if r["op"] == "redesign_character"}
    for cid in d["designs_changed"]:
        if cid not in redesigned:
            issues.append({"check": "character_design_changed", "detail": cid})
    current = character_designs()
    for cid, h in draft["characters"]["designs"].items():
        if current.get(cid) != h:
            issues.append({"check": "bible_differs_from_state", "detail": f"{cid}: bible look changed without "
                                                                          f"a 'redesign_character' event"})
    return issues


def check_scene_inventory(state: dict, inventory: dict) -> list[dict]:
    """The saved Blender scene must contain exactly the state's objects with the recorded transforms/texts."""
    issues = []
    inv = inventory.get("objects", {})
    for o in state["objects"]:
        got = inv.get(o["id"])
        if got is None:
            issues.append({"check": "missing_in_scene", "detail": o["id"]})
            continue
        if any(abs(a - b) > 1e-3 for a, b in zip(got["loc"], o["loc"])):
            issues.append({"check": "position_mismatch", "detail": f"{o['id']}: {got['loc']} != {o['loc']}"})
        if o["kind"] == "text" and got.get("body") != o["body"]:
            issues.append({"check": "text_mismatch", "detail": o["id"]})
        expected = (o["material"]["name"] if o.get("material") else f"text_{o['colour']}" if o["kind"] == "text" else "")
        if o["kind"] != "light" and got.get("material", "") != expected:
            issues.append({"check": "material_mismatch", "detail": f"{o['id']}: {got.get('material')} != {expected}"})
    extra = set(inv) - {o["id"] for o in state["objects"]}
    for oid in sorted(extra):
        issues.append({"check": "unexpected_in_scene", "detail": oid})
    return issues


def compare_reference_images(parent_refs: Path, draft_refs: Path, changed_locations: set[str],
                             tolerance: float = 0.05) -> list[dict]:
    """Pixel comparison of the fixed reference cameras. Unchanged locations must look the same."""
    import numpy as np
    from PIL import Image
    issues = []
    for ref in sorted(Path(parent_refs).glob("*.png")):
        loc = ref.stem
        other = Path(draft_refs) / ref.name
        if not other.is_file():
            issues.append({"check": "reference_missing", "detail": loc})
            continue
        a = np.asarray(Image.open(ref).convert("RGB"), dtype=np.float32)
        b = np.asarray(Image.open(other).convert("RGB"), dtype=np.float32)
        if a.shape != b.shape:
            issues.append({"check": "reference_size_changed", "detail": loc})
            continue
        mean_diff = float(np.abs(a - b).mean())
        if loc not in changed_locations and mean_diff > tolerance:
            issues.append({"check": "visual_change_without_story_event",
                           "detail": f"{loc}: mean pixel difference {mean_diff:.2f} > {tolerance}"})
    return issues


# --- versions -----------------------------------------------------------------------------------------
class CityStore:
    def __init__(self, db: Database, root: Path):
        self.db = db
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def folder(self, n: int) -> Path:
        return self.root / version_name(n)

    def load_state(self, n: int) -> dict:
        return json.loads((self.folder(n) / "state.json").read_text(encoding="utf-8"))

    def row(self, n: int) -> dict | None:
        return self.db.query_one("SELECT * FROM city_versions WHERE number=?", (n,))

    def versions(self) -> list[dict]:
        return self.db.query("SELECT * FROM city_versions ORDER BY number")

    def latest_approved(self) -> int | None:
        return self.db.scalar("SELECT MAX(number) FROM city_versions WHERE status='approved'")

    def _next_number(self) -> int:
        return (self.db.scalar("SELECT MAX(number) FROM city_versions") or 0) + 1

    def _write(self, n: int, state: dict, changes: list[dict], parent: int | None, episode_id: str | None) -> Path:
        f = self.folder(n)
        if f.exists() and (f / "state.json").exists():
            raise FileExistsError(f"{version_name(n)} already exists – versions are never overwritten")
        f.mkdir(parents=True, exist_ok=True)
        (f / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        (f / "changes.json").write_text(json.dumps(changes, ensure_ascii=False, indent=2), encoding="utf-8")
        (f / "manifest.json").write_text(json.dumps({
            "version": version_name(n), "parent": version_name(parent) if parent else None, "episode": episode_id,
            "state_hash": state_hash(state), "objects": len(state["objects"]), "created_at": utcnow()},
            indent=2), encoding="utf-8")
        return f

    def create_baseline(self) -> int:
        """Bobbington_City_v001 from the canonical seed (only if no version exists yet)."""
        if self.db.scalar("SELECT COUNT(*) FROM city_versions"):
            raise RuntimeError("baseline already exists")
        state = seed_state()
        state["characters"] = {"designs": character_designs(), "last_positions": {}}
        state["version"] = version_name(1)
        self._write(1, state, [{"op": "baseline", "reason": "canonical starting state from the series bible"}], None, None)
        self.db.execute("INSERT INTO city_versions (number, parent, status, state_hash, changes_json, folder, note, "
                        "created_at) VALUES (1, NULL, 'draft', ?, ?, ?, ?, ?)",
                        (state_hash(state), json.dumps([{"op": "baseline"}]), str(self.folder(1)),
                         "baseline – approve after checking the reference renders", utcnow()))
        return 1

    def create_draft(self, parent: int, changes: list[CityChange], episode_id: str,
                     final_positions: dict | None = None) -> tuple[int, dict, list[dict]]:
        prow = self.row(parent)
        if not prow or prow["status"] != "approved":
            raise ValueError(f"{version_name(parent)} is not approved – episodes must start from an approved version")
        state, records = apply_changes(self.load_state(parent), changes)
        state["version"] = version_name(self._next_number())
        if final_positions:
            state["characters"]["last_positions"] = final_positions
        n = self._next_number()
        self._write(n, state, records, parent, episode_id)
        self.db.execute("INSERT INTO city_versions (number, parent, status, episode_id, state_hash, changes_json, folder,"
                        " created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (n, parent, "draft", episode_id, state_hash(state), json.dumps(records), str(self.folder(n)),
                         utcnow()))
        return n, state, records

    def record_continuity(self, n: int, issues: list[dict]) -> None:
        self.db.execute("UPDATE city_versions SET continuity_json=? WHERE number=?", (json.dumps(issues), n))
        manifest = self.folder(n) / "manifest.json"
        m = json.loads(manifest.read_text(encoding="utf-8"))
        m["continuity"] = {"passed": not issues, "issues": issues, "checked_at": utcnow()}
        manifest.write_text(json.dumps(m, indent=2), encoding="utf-8")

    def link_video(self, n: int, video_id: str) -> None:
        self.db.execute("UPDATE city_versions SET video_id=? WHERE number=?", (video_id, n))

    def approve(self, n: int) -> None:
        row = self.row(n)
        if not row:
            raise KeyError(n)
        if row["status"] != "draft":
            raise ValueError(f"{version_name(n)} is {row['status']}")
        if row["continuity_json"] is None or json.loads(row["continuity_json"]):
            raise ValueError(f"{version_name(n)}: continuity check missing or failed – cannot approve")
        latest = self.latest_approved()
        if row["parent"] is not None and row["parent"] != latest:
            raise ValueError(f"{version_name(n)} was built on {version_name(row['parent'])}, but the current approved "
                             f"version is {version_name(latest)} – re-render the episode on the current town")
        for required in ("state.json", "scene.blend", "inventory.json"):
            if not (self.folder(n) / required).is_file():
                raise ValueError(f"{version_name(n)}: {required} missing")
        self.db.execute("UPDATE city_versions SET status='approved', approved_at=? WHERE number=?", (utcnow(), n))

    def reject(self, n: int, note: str = "") -> None:
        if self.row(n)["status"] == "draft":
            self.db.execute("UPDATE city_versions SET status='rejected', note=? WHERE number=?", (note, n))

    def restore(self, n: int, reason: str) -> int:
        """Makes an older approved version the basis again – as a NEW version (history is never rewritten)."""
        row = self.row(n)
        if not row or row["status"] != "approved":
            raise ValueError("only approved versions can be restored")
        state = self.load_state(n)
        new_n = self._next_number()
        state["version"] = version_name(new_n)
        rec = [{"op": "restore", "restored_from": version_name(n), "reason": reason}]
        self._write(new_n, state, rec, self.latest_approved(), None)
        import shutil
        for name in ("scene.blend", "inventory.json"):
            if (self.folder(n) / name).is_file():
                shutil.copy(self.folder(n) / name, self.folder(new_n) / name)
        if (self.folder(n) / "refs").is_dir():
            shutil.copytree(self.folder(n) / "refs", self.folder(new_n) / "refs")
        self.db.execute("INSERT INTO city_versions (number, parent, status, state_hash, changes_json, folder, note,"
                        " created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (new_n, self.latest_approved(), "draft", state_hash(state), json.dumps(rec),
                         str(self.folder(new_n)), f"restore of {version_name(n)}: {reason}", utcnow()))
        self.record_continuity(new_n, [])
        return new_n

    def changed_locations(self, records: list[dict]) -> set[str]:
        locs = set()
        for r in records:
            if r.get("group"):
                locs.add(r["group"].split("/")[0])
            if r["op"] == "set_environment":
                locs.update(["mayors_office", "council_chamber", "main_street", "pub"])
        return locs
