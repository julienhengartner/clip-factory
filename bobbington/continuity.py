"""Episode-to-episode city workflow and continuity validation.

1. load the latest APPROVED city version (creating/validating Bobbington_City_v001 once if none exists)
2. derive the draft version: open the approved scene.blend and apply ONLY the episode's declared story events
3. continuity checks (all must pass before an episode can be approved):
   - state: every difference to the parent is explained by a declared event; marks, reference cameras and
     character designs unchanged (unless declared)
   - scene: the saved scene.blend contains exactly the state's objects (positions, materials, texts)
   - visual: reference renders of locations without story events are pixel-identical (tolerance)
4. the episode is rendered from the PARENT scene with the events appearing at their shots
5. on approval of the video the draft becomes the new approved version; on rejection it is discarded
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from bobbington.citystate import (CityChange, CityStore, check_scene_inventory, check_state_continuity,
                                  compare_reference_images, version_name)
from bobbington.episode import Episode
from config import Settings
from storage.database import Database

ROOT = Path(__file__).resolve().parent.parent


class ContinuityError(RuntimeError):
    def __init__(self, version: str, issues: list[dict]):
        self.version, self.issues = version, issues
        super().__init__(f"{version}: continuity check failed – " + "; ".join(f"{i['check']}: {i['detail']}"
                                                                              for i in issues[:8]))


def final_positions(episode: Episode) -> dict:
    """Where every character was last seen – continuity detail stored with the city version."""
    out = {}
    for shot in episode.shots:
        for cid, mark in shot.cast.items():
            out[cid] = {"location": shot.set, "mark": mark, "episode": episode.id, "shot": shot.id}
    return out


class CityManager:
    def __init__(self, settings: Settings, db: Database):
        self.s = settings
        self.store = CityStore(db, settings.data_dir / "city")
        self.archive_dir = settings.city_archive_dir

    def _blender(self, *args: str) -> str:
        cmd = [str(self.s.blender_bin), "-b", "--factory-startup", "-P", str(ROOT / "blender" / "build_city.py"),
               "--", *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        if proc.returncode != 0 or "CITY_BUILT" not in proc.stdout:
            raise RuntimeError("Blender city build failed:\n" + "\n".join((proc.stdout + proc.stderr).splitlines()[-20:]))
        return proc.stdout

    def ensure_baseline(self) -> int:
        latest = self.store.latest_approved()
        if latest:
            return latest
        if not self.store.versions():
            self.store.create_baseline()
        folder = self.store.folder(1)
        if not (folder / "scene.blend").is_file():
            self._blender("build", str(folder))
        state = self.store.load_state(1)
        inv = json.loads((folder / "inventory.json").read_text(encoding="utf-8"))
        issues = check_scene_inventory(state, inv)
        self.store.record_continuity(1, issues)
        if issues:
            raise ContinuityError(version_name(1), issues)
        self.store.approve(1)
        self.archive(1)
        return 1

    def prepare(self, episode: Episode) -> dict:
        """Creates and validates the draft version for an episode. Raises ContinuityError if anything is off."""
        base = self.ensure_baseline()
        changes = [CityChange(**c) for c in episode.city_changes]
        reuse = self._existing_draft(base, episode)
        if reuse:
            return reuse
        n, state, records = self.store.create_draft(base, changes, episode.id, final_positions(episode))
        draft, parent = self.store.folder(n), self.store.folder(base)
        self._blender("derive", str(draft), str(parent))
        issues = check_state_continuity(self.store.load_state(base), state, records)
        issues += check_scene_inventory(state, json.loads((draft / "inventory.json").read_text(encoding="utf-8")))
        issues += compare_reference_images(parent / "refs", draft / "refs", self.store.changed_locations(records))
        self.store.record_continuity(n, issues)
        if issues:
            self.store.reject(n, "continuity check failed")
            raise ContinuityError(version_name(n), issues)
        return {"base_version": version_name(base), "draft_version": version_name(n), "draft_number": n,
                "base_blend": str(parent / "scene.blend"), "draft_state": str(draft / "state.json"),
                "records": records}

    def _existing_draft(self, base: int, episode: Episode) -> dict | None:
        """A validated draft for the same episode on the same baseline is reused (no duplicate versions)."""
        from bobbington.citystate import apply_changes
        expected, _ = apply_changes(self.store.load_state(base), [CityChange(**c) for c in episode.city_changes])
        for r in reversed(self.store.versions()):
            if r["episode_id"] == episode.id and r["parent"] == base and r["status"] == "draft"                     and r["continuity_json"] == "[]":
                st = self.store.load_state(r["number"])
                if st["objects"] == expected["objects"] and st["environment"] == expected["environment"]:
                    folder = self.store.folder(r["number"])
                    return {"base_version": version_name(base), "draft_version": version_name(r["number"]),
                            "draft_number": r["number"], "base_blend": str(self.store.folder(base) / "scene.blend"),
                            "draft_state": str(folder / "state.json"), "records": json.loads(r["changes_json"]),
                            "reused": True}
        return None

    def approve(self, n: int) -> None:
        self.store.approve(n)
        self.archive(n)

    def archive(self, n: int) -> Path:
        """Approved versions are copied into the repository folder city/ (committed to GitHub = off-site backup).
        Existing archive folders are never overwritten."""
        import shutil
        if self.store.row(n)["status"] != "approved":
            raise ValueError("only approved versions are archived")
        target = self.archive_dir / version_name(n)
        if not target.exists():
            shutil.copytree(self.store.folder(n), target)
        return target

    def reject(self, n: int, note: str = "") -> None:
        self.store.reject(n, note)

    def status(self) -> dict:
        rows = self.store.versions()
        return {"approved": version_name(self.store.latest_approved()) if self.store.latest_approved() else None,
                "versions": [{"version": version_name(r["number"]), "status": r["status"], "episode": r["episode_id"],
                              "continuity": "passed" if r["continuity_json"] == "[]" else
                              ("failed" if r["continuity_json"] else "not checked")} for r in rows]}


def main(argv: list[str] | None = None) -> int:
    """python -m bobbington.continuity status | restore <number> <reason>"""
    import argparse
    import sys
    from config import get_settings
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Bobbington city versions")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    r = sub.add_parser("restore", help="make an older approved version the basis again (as a new version)")
    r.add_argument("number", type=int)
    r.add_argument("reason")
    ap = sub.add_parser("approve-restore", help="approve a restore version (episode versions are approved via the video)")
    ap.add_argument("number", type=int)
    a = p.parse_args(argv)
    s = get_settings()
    m = CityManager(s, Database(s.db_path))
    if a.cmd == "status":
        print(json.dumps(m.status(), indent=2, ensure_ascii=False))
    elif a.cmd == "approve-restore":
        row = m.store.row(a.number)
        if not row or row["episode_id"]:
            print("only restore versions can be approved here – episode versions are approved with their video")
            return 1
        m.approve(a.number)
        print(f"{version_name(a.number)} is now the approved Bobbington baseline")
    else:
        n = m.store.restore(a.number, a.reason)
        print(f"{version_name(n)} created from {version_name(a.number)} – approve it to make it the baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
