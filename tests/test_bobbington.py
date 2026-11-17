"""Bobbington: bible, episode format, generator, city simulation, timeline/length fitting, sound, brand, rig."""
import json
import shutil
import subprocess
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from bobbington import sound
from bobbington.bible import CAST, PALETTE, TOWN
from bobbington.docs import generate as generate_docs
from bobbington.episode import Episode, load_episode
from bobbington.generator import PREMISES, build_episode, choose_premise, generate
from bobbington.simulation import START_BALANCE_PENCE, CitySimulation, InsufficientFundsError, gbp
from bobbington.timeline import TimelineBuilder, chunk_text, mix_audio
from bobbington.voices import VOICE_CREDITS, mouth_envelope, speech_bounds
from config import Settings
from storage.database import Database

ROOT = Path(__file__).resolve().parent.parent
PILOT = ROOT / "episodes" / "pilot_mayor_bans_mondays.json"
BLENDER = Settings(_env_file=None).blender_bin


class FakeVoices:
    """Deterministic stand-in for Piper: 0.38 s per word of a voiced tone (no external tools)."""

    def __init__(self, tmp: Path, seconds_per_word: float = 0.38):
        self.tmp, self.spw = tmp, seconds_per_word

    def synthesize(self, character: str, text: str) -> Path:
        path = self.tmp / f"{abs(hash((character, text, self.spw)))}.wav"
        if not path.exists():
            sr = 22050
            n = int(sr * (0.1 + self.spw * len(text.split())))
            t = np.arange(n) / sr
            x = 0.4 * np.sin(2 * np.pi * 160 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
            x[: int(0.05 * sr)] = 0
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes((x * 32767).astype(np.int16).tobytes())
        return path


# --- bible ---------------------------------------------------------------------------------
def test_bible_is_complete_and_consistent():
    assert set(CAST) == {"winston", "margaret", "reginald", "brenda", "arthur", "nigel"}
    assert CAST["winston"]["name"] == "Mayor Winston Boggle"
    w = CAST["winston"]["look"]
    assert w["moustache"]["style"] == "bushy_handlebar" and w["glasses"]["style"] == "round"
    assert w["outfit"]["neck"]["type"] == "bow_tie" and w["outfit"]["jacket_pattern"] == "tweed"
    for cid, c in CAST.items():
        assert c["voice"]["model"] in VOICE_CREDITS, cid           # only voices with a known licence
        assert set(c["relationships"]) == set(CAST) - {cid}, cid   # every relationship defined
    assert all(len(v) == 7 and v.startswith("#") for v in PALETTE.values())
    assert TOWN["starting_population"] == 2450 and TOWN["starting_budget_gbp"] == 1_000_000


def test_brand_assets_and_bible_doc(tmp_path):
    files = generate_docs(tmp_path)
    for f in files[:3]:
        root = ET.parse(f).getroot()
        assert root.tag.endswith("svg")
    doc = files[3].read_text(encoding="utf-8")
    assert "A Town Full of Bad Decisions." in doc and "Inspector Nigel Nonsense" in doc


# --- episode format & generator --------------------------------------------------------------
def test_pilot_is_valid_and_structured():
    ep = load_episode(PILOT)
    assert ep.title == "THE MAYOR BANS MONDAYS!"
    assert set(ep.structure) >= {"beginning", "conflict", "escalation", "twist", "punchline"}
    assert ep.shots[0].lines[0].speaker == "winston"
    assert len(ep.shots[0].lines[0].text.split()) <= 8   # hook fits into the first 3 seconds


@pytest.mark.parametrize("mutation, error", [
    (lambda d: d["shots"][0]["lines"][0].update(speaker="mr_nobody"), "unknown speaker"),
    (lambda d: d["shots"][0]["lines"][0].update(action="moonwalk"), "unknown action"),
    (lambda d: d["structure"].pop("twist"), "structure incomplete"),
    (lambda d: d["shots"][0].update(set="mars"), "unknown set"),
])
def test_episode_validation_rejects_bad_scripts(mutation, error):
    data = json.loads(PILOT.read_text(encoding="utf-8"))
    mutation(data)
    with pytest.raises(ValueError, match=error):
        Episode.model_validate(data)


def test_generator_builds_valid_episodes_and_never_repeats(tmp_path):
    for i, p in enumerate(PREMISES, start=2):
        ep = build_episode(p, i)
        assert ep.id == f"s01e{i:02d}" and ep.shots[0].lines[0].speaker == "winston"
    hot = {"open_complaints": [{"department": "Public Works"}]}
    assert choose_premise(set(), hot)["id"] == "roundabout"          # simulation steers the story
    assert choose_premise({p["id"] for p in PREMISES}) is None
    path = generate(tmp_path, {"rain"}, 2)
    assert Episode.model_validate(json.loads(path.read_text(encoding="utf-8"))).id == "s01e02"


# --- city simulation -----------------------------------------------------------------------------
@pytest.fixture
def sim(tmp_path):
    return CitySimulation(Database(tmp_path / "sim.db"))


def test_simulation_start_values_and_ledger(sim):
    assert sim.population == 2450 and sim.balance_pence == START_BALANCE_PENCE
    e = sim.post("Public Works", "expense", 12_345, "Traffic cones (emergency supply)", "test")
    assert e.balance_after_pence == START_BALANCE_PENCE - 12_345
    with pytest.raises(InsufficientFundsError):
        sim.post("Public Works", "expense", START_BALANCE_PENCE * 2, "Gold-plated roundabout")
    with pytest.raises(ValueError):
        sim.post("Ministry of Silly Walks", "expense", 100, "x")
    assert sim.audit() and gbp(123456) == "£1,234.56"


def test_simulation_advances_reproducibly(tmp_path):
    a = CitySimulation(Database(tmp_path / "a.db"), seed=7)
    b = CitySimulation(Database(tmp_path / "b.db"), seed=7)
    ra, rb = a.advance(14), b.advance(14)
    assert ra == rb and a.population == b.population and a.balance_pence == b.balance_pence
    assert ra["revenue"] > 0 and ra["expenses"] > 0 and a.audit()
    totals = a.department_totals()
    assert totals["Treasury"]["revenue"] > 0 and "Police" in totals


def test_projects_votes_complaints(sim):
    pid = sim.start_project("Historic Puddle Restoration", "Parks & Traditions", 500_000)
    sim.spend_on_project(pid, 120_000, "Puddle consultant")
    assert sim.db.query_one("SELECT spent_pence FROM sim_projects WHERE id=?", (pid,))["spent_pence"] == 120_000
    assert sim.ledger(f"project:{pid}")[0]["amount_pence"] == 120_000
    vid = sim.open_vote("Should Mondays return?", ["Yes", "No"], method="citizens")
    r1 = sim.close_vote(vid, bias={"Yes": 2.0})
    assert sum(r1.values()) > 0 and r1["Yes"] > r1["No"]
    cid = sim.complain("Waste & Recycling", "Bins not collected")
    assert sim.get("mood") == -1
    sim.resolve_complaint(cid)
    assert sim.get("mood") == 0


def test_episode_effects_applied_once(sim):
    ep = load_episode(PILOT)
    first = sim.apply_episode(ep.id, ep.sim_effects)
    second = sim.apply_episode(ep.id, ep.sim_effects)
    assert first["status"] == "applied" and second["status"] == "already_applied"
    assert len(sim.ledger(f"episode:{ep.id}")) == 2
    assert len(sim.report()["open_complaints"]) == 2 and sim.audit()


def test_simulation_is_separate_from_followers(sim, tmp_path):
    from brain.memory import Memory
    mem = Memory(sim.db)
    mem.add_follower_stats("instagram", 99_999, 0, 0)
    assert sim.population == 2450   # real followers never change simulated residents


# --- timeline, length fitting, audio ------------------------------------------------------------
def test_chunking_keeps_all_words():
    text = "Citizens of Bobbington! Mondays have caused misery since records began. Today, I end them."
    chunks = chunk_text(text)
    assert " ".join(chunks).split() == text.split() and all(len(c.split()) <= 5 for c in chunks)


def test_timeline_fits_length_with_script_changes(tmp_path):
    ep = load_episode(PILOT)
    slow = TimelineBuilder(FakeVoices(tmp_path, 0.5))      # too long -> optional line dropped
    _, tl = slow.fit(ep, 60, 75, 120)
    assert any("dropped optional" in a for a in tl.adjustments) or tl.duration <= 75
    fast = TimelineBuilder(FakeVoices(tmp_path, 0.24))     # too short -> extensions added
    ep2, tl2 = fast.fit(ep, 58, 75, 80)
    assert any("extension" in a for a in tl2.adjustments)
    assert sum(len(s.lines) for s in ep2.shots) > sum(len(s.lines) for s in ep.shots)
    with pytest.raises(ValueError, match="too short"):
        TimelineBuilder(FakeVoices(tmp_path, 0.1)).fit(ep, 60, 75, 80)


def test_timeline_frames_subtitles_and_mix(tmp_path):
    ep = load_episode(PILOT)
    tb = TimelineBuilder(FakeVoices(tmp_path, 0.4))
    ep2, tl = tb.fit(ep, 60, 80, 90)
    assert tl.total_frames == round(tl.duration * 24)
    frames = [(s.start_frame, s.end_frame) for s in tl.shots]
    assert all(a[1] == b[0] for a, b in zip(frames, frames[1:]))              # gapless cuts
    words = sum(len(l.text.split()) for s in tl.shots for l in s.lines)
    assert sum(len(c.text.split()) for c in tl.subtitles) == words            # every word subtitled
    assert all(a.end <= b.start + 1e-6 for a, b in zip(tl.subtitles, tl.subtitles[1:]))
    assert tl.shots[0].lines[0].speech_end < 3.0                               # hook in 3 seconds
    line = tl.shots[0].lines[0]
    assert len(line.mouth) >= line.end_frame - line.start_frame - 1 and max(line.mouth) == 1.0
    wav = mix_audio(ep2, tl, tmp_path / "mix.wav")
    with wave.open(str(wav)) as w:
        assert abs(w.getnframes() / w.getframerate() - tl.duration) < 0.05


def test_mouth_envelope_and_bounds():
    sr = 22050
    x = np.concatenate([np.zeros(sr // 4), 0.5 * np.sin(np.arange(sr) * 0.05), np.zeros(sr // 4)])
    a, b = speech_bounds(x, sr)
    assert 0.2 < a < 0.3 and 1.2 < b < 1.3
    env = mouth_envelope(x, sr, 24)
    assert env[0] == 0 and max(env) == 1.0 and len(env) == int(np.ceil(len(x) / (sr / 24)))


def test_sound_library_is_audible(tmp_path):
    lib = sound.build_library(tmp_path)
    for name, path in lib.items():
        with wave.open(str(path)) as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        assert np.abs(data).max() > 1000, name


# --- Blender rig (real Blender, skipped if not installed) ----------------------------------------
@pytest.mark.skipif(not Path(BLENDER).is_file(), reason="Blender not installed")
def test_blender_builds_rigged_cast(tmp_path):
    script = tmp_path / "probe.py"
    script.write_text(f'''
import sys, json
sys.path[:0] = [r"{ROOT}", r"{ROOT / "blender"}"]
import bpy
from bobbington.bible import CAST, PALETTE
import characters, scene_kit
scene_kit.reset_scene()
out = {{}}
for cid in CAST:
    c = characters.build_character(cid, CAST[cid], PALETTE)
    out[cid] = {{"bones": sorted(b.name for b in c["rig"].data.bones), "parts": len(c["parts"]),
                 "has_mouth": "mouth" in c["parts"], "height": round(c["dims"]["height"], 2)}}
print("PROBE=" + json.dumps(out))
''', encoding="utf-8")
    proc = subprocess.run([str(BLENDER), "-b", "--factory-startup", "-P", str(script)], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=300)
    line = next(l for l in proc.stdout.splitlines() if l.startswith("PROBE="))
    probe = json.loads(line[6:])
    for cid, info in probe.items():
        assert {"root", "spine", "head", "arm.L", "arm.R", "leg.L", "leg.R", "brow.L", "brow.R"} <= set(info["bones"])
        assert info["has_mouth"] and info["parts"] >= 20
        assert info["height"] == CAST[cid]["look"]["height"]


def test_brain_produces_pilot_first_then_generated_episodes(tmp_path, monkeypatch):
    from bobbington.production import EpisodeProducer
    from brain.orchestrator import BrainAgent
    from storage.models import QCCheck, QCReport
    from tests.conftest import make_settings
    from tests.fakes import wiki_transport
    produced = []

    def fake_produce(self, path, quality="final", **kw):
        """Real city versioning, but without Blender: scene files are stand-ins."""
        from bobbington.citystate import CityChange, CityStore, version_name
        from storage.database import Database
        produced.append(Path(path).name)
        ep = load_episode(path)
        store = CityStore(Database(self.s.db_path), self.s.data_dir / "city")
        if not store.versions():
            store.create_baseline()
            for f in ("scene.blend", "inventory.json"):
                (store.folder(1) / f).write_text("{}", encoding="utf-8")
            store.record_continuity(1, [])
            store.approve(1)
        base = store.latest_approved()
        n, _, _ = store.create_draft(base, [CityChange(**c) for c in ep.city_changes], ep.id)
        for f in ("scene.blend", "inventory.json"):
            (store.folder(n) / f).write_text("{}", encoding="utf-8")
        store.record_continuity(n, [])
        video = tmp_path / f"{len(produced)}.mp4"
        video.write_bytes(b"x")
        report = QCReport(checks=[QCCheck(name="length_minimum", passed=True, detail="ok", value=70.0)])
        return {"episode": ep, "qc": report, "video": video, "thumbnail": video, "quality": quality,
                "city": {"base_version": version_name(base), "draft_version": version_name(n), "draft_number": n}}

    monkeypatch.setattr(EpisodeProducer, "produce", fake_produce)
    brain = BrainAgent(make_settings(tmp_path, content_mode="bobbington"), http_transport=wiki_transport({}))
    v1 = brain.produce()
    assert produced[0] == "pilot_mayor_bans_mondays.json" and v1["status"] == "ready"
    v2 = brain.produce()
    assert produced[1].startswith("s01e0") and produced[1] != produced[0]
    v3 = brain.produce()
    assert produced[2] != produced[1]                                  # no premise twice
    brain.approve(v1["id"])                                             # approval writes the story into the town
    from bobbington.simulation import CitySimulation
    assert len(CitySimulation(brain.db).ledger("episode:s01e01")) == 2
    from bobbington.citystate import CityStore
    store = CityStore(brain.db, brain.s.data_dir / "city")
    assert store.latest_approved() == 2                                 # the pilot's town is the new baseline
    import pytest as _pytest
    from core.errors import FactoryError
    with _pytest.raises(FactoryError, match="re-render"):
        brain.approve(v2["id"])                                         # built on v001 -> must be re-rendered
    brain.reject(v3["id"], "not funny")
    assert store.row(v3["episode"]["city_version"]["draft_number"])["status"] == "rejected"


def test_chunked_render_resumes_after_interruption(tmp_path, monkeypatch):
    from bobbington.production import EpisodeProducer
    from tests.conftest import make_settings
    from video_engine.ffmpeg import run_ffmpeg
    tl = tmp_path / "timeline.json"
    tl.write_text(json.dumps({"total_frames": 60}), encoding="utf-8")
    calls = []

    def fake_range(self, timeline_json, out, quality, first, last):
        calls.append((first, last))
        n = last - first + 1
        run_ffmpeg(["-f", "lavfi", "-i", f"testsrc=size=64x112:rate=24", "-frames:v", str(n), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(out)])
        return out

    monkeypatch.setattr(EpisodeProducer, "_render_range", fake_range)
    prod = EpisodeProducer(make_settings(tmp_path))
    out = prod.render(tl, tmp_path / "render.mp4", "draft", chunk_frames=25)
    assert calls == [(0, 24), (25, 49), (50, 59)] and out.is_file()
    # interruption: one chunk is broken -> only that chunk is rendered again
    broken = sorted((tmp_path / "render_chunks").glob("chunk_01_*.mp4"))[0]
    broken.write_bytes(b"half a file")
    calls.clear()
    prod.render(tl, tmp_path / "render.mp4", "draft", chunk_frames=25)
    assert calls == [(25, 49)]
