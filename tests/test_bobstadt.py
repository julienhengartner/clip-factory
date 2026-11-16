"""Bobstadt-Modus: Stadtzustand, Community-Stimmen, Episodenplanung, Grafik, Planung, Ende-zu-Ende."""
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

from agents.base import AgentContext
from agents.hook import HookAgent
from agents.script_writer import ScriptWriterAgent
from brain.city import City, fmt_eur, fmt_int
from brain.episodes import EpisodePlanner
from brain.orchestrator import BrainAgent
from core.errors import FactoryError
from core.text import word_count
from integrations.http import make_client
from integrations.token_store import TokenStore
from storage.models import HookCandidate, Idea
from tests.conftest import make_settings, requires_windows_tts
from tests.fakes import wiki_transport
from tests.test_agents import FakeTikTok
from video_engine.isometric import render_build_frames, render_city, slots

FREIBAD = (
    "Ein Freibad ist eine im Freien angelegte öffentliche Badeanstalt. "
    "Neben den Becken gehören meist Liegewiesen, Umkleiden und ein Kiosk zur Anlage. "
    "Die Becken sind häufig fünfundzwanzig oder fünfzig Meter lang. "
    "Viele Freibäder öffnen nur in den warmen Monaten des Jahres. "
    "Aufsichtspersonen achten darauf, dass beim Baden niemand in Gefahr gerät. "
    "In vielen Gemeinden gehört das Freibad zu den beliebtesten Treffpunkten im Sommer. "
    "Manche Anlagen besitzen Sprungtürme, Rutschen und eigene Bereiche für Kinder. "
    "Das Wasser wird ständig gefiltert und mit Chlor desinfiziert.")


@pytest.fixture
def city(settings, memory):
    c = City(settings, memory)
    c.ensure_seed()
    return c


def comment(memory, cid, text, author, category="sonstiges"):
    memory.upsert_comment("instagram", cid, text, "m1", author, 0, None)
    row = memory.db.query_one("SELECT id FROM comments WHERE external_id=?", (cid,))
    memory.set_comment_analysis(row["id"], category, 0.0, [])


# --- Stadtzustand ----------------------------------------------------------------------
def test_number_formatting():
    assert fmt_int(13400) == "13.400"
    assert fmt_eur(1_500_000) == "1,5 Millionen Euro" and fmt_eur(1_000_000) == "1 Million Euro"
    assert fmt_eur(4_380_000) == "4,38 Millionen Euro" and fmt_eur(150_000) == "150.000 Euro"


def test_seed_is_unconfirmed_and_budget_rule(city):
    st = city.state()
    assert st.residents == 13_400 and st.budget_eur == 13_400_000
    assert st.available_eur == st.budget_eur - st.spent_eur
    assert st.confirmed is False and all(not b["confirmed"] for b in st.buildings)
    city.ensure_seed()  # idempotent
    assert len(city.state().buildings) == 5


def test_instagram_followers_override_manual_value(city, memory):
    memory.add_follower_stats("instagram", 14_210, 0, 50)
    st = city.state()
    assert st.residents == 14_210 and "Instagram" in st.residents_source


def test_confirm_and_adjust(city):
    city.set_residents(13_512)
    city.set_spent_adjust(-500_000)
    city.confirm()
    st = city.state()
    assert st.confirmed and st.residents == 13_512
    assert st.spent_eur == sum(b["cost_eur"] for b in st.buildings) - 500_000


def test_match_building(city):
    assert city.match_building("Baut endlich ein Freibad!!").key == "freibad"
    assert city.match_building("Wir brauchen eine Feuerwehr") .key == "feuerwache"
    assert city.match_building("Toll gemacht") is None


def test_votes_one_per_person_and_no_spam(city, memory):
    comment(memory, "c1", "Freibad bitte!", "anna")
    comment(memory, "c2", "Freibad, Freibad, Freibad", "anna")         # gleiche Person -> 1 Stimme
    comment(memory, "c3", "Ich will ein Schwimmbad", "ben")
    comment(memory, "c4", "Freibad gratis follower www.x.y", "spam1", category="spam")
    comment(memory, "c5", 'Name: "Sonnenhang"', "carla")
    counted = city.collect_votes()
    assert counted["building"] == 3
    props = {p["value"]: p["votes"] for p in memory.proposals("building")}
    assert props == {"freibad": 2}
    assert memory.proposals("name")[0]["value"] == "Sonnenhang"
    assert city.collect_votes() == {"building": 0, "name": 0}  # nichts doppelt zählen


# --- Episodenplanung -------------------------------------------------------------------
def test_planner_wish_affordable_or_funding(city, memory):
    planner = EpisodePlanner(city, memory, random.Random(1))
    ep = planner.plan(wish="Freibad")
    assert ep.type == "bau" and ep.effects["build"] == "freibad"
    assert any("1,5 Millionen Euro" in p.text for p in ep.plot)
    ep2 = planner.plan(wish="Flughafen")  # 8 Mio. > Kasse
    assert ep2.type == "finanzierung" and ep2.effects == {}
    gap = 8_000_000 - city.state().available_eur
    assert any(fmt_int(gap // 1000) in p.text for p in ep2.plot)  # fehlende Einwohner exakt berechnet
    assert planner.plan(wish="Mondbasis") is None


def test_planner_priorities(city, memory):
    planner = EpisodePlanner(city, memory, random.Random(1))
    assert planner.plan().type == "abstimmung"  # keine Wünsche -> Community fragen
    memory.add_follower_stats("instagram", 14_020, 0, 0)  # Meilenstein 14.000 überschritten
    ep = planner.plan()
    assert ep.type == "meilenstein" and ep.effects["milestone"] == 14_000
    memory.set_setting("city.last_milestone", 14_000)
    for who in ("a", "b"):
        memory.vote("building", "kino", who)
    assert planner.plan().type == "bau" and planner.plan().building == "kino"


def test_episode_effects_only_on_approval(tmp_path):
    brain = BrainAgent(make_settings(tmp_path), http_transport=wiki_transport({}))
    ep = brain.planner.plan(wish="Kino")
    for status, expect_built in (("rejected", False), ("approved", True)):
        v = brain.memory.create_video("Kino")
        brain.memory.update_video(v["id"], status="ready", episode_json=ep.model_dump())
        if status == "approved":
            brain.approve(v["id"])
        else:
            brain.reject(v["id"])
        built = [b["kind"] for b in brain.memory.buildings("built")]
        assert ("kino" in built) == expect_built


# --- Skript & Hook -----------------------------------------------------------------------
@pytest.fixture
def ctx(settings, memory, budget):
    return AgentContext(settings=settings, memory=memory, budget=budget, http=make_client(settings),
                        tokens=TokenStore(settings.secrets_dir))


def test_episode_script_keeps_plot_when_expanding_and_shortening(ctx, city, memory):
    ep = EpisodePlanner(city, memory, random.Random(1)).plan(wish="Freibad")
    w = ScriptWriterAgent(ctx)
    from core.text import split_sentences
    material = split_sentences(FREIBAD)
    script = w.write_episode(ep, material, HookCandidate(text="Bobstadt bekommt das Freibad!", pattern="ep_bau_0"), 140)
    roles = [s.role for s in script.segments]
    assert roles[0] == "hook" and roles[-1] == "cta" and roles.count("plot") == len(ep.plot)
    idea = Idea(title=ep.title, angle="bau")
    longer = w.expand(script, idea, material, 40)
    shorter = w.shorten(longer, idea, 999)
    for s in (longer, shorter):
        assert [x.text for x in s.segments if x.role == "plot"] == [p.text for p in ep.plot]
        assert s.segments[-1].role == "cta"
    assert longer.word_count > script.word_count > shorter.word_count


def test_episode_hooks(ctx, city, memory):
    ep = EpisodePlanner(city, memory, random.Random(1)).plan(wish="Freibad")
    best, cands = HookAgent(ctx).choose_episode(ep, wpm=136)
    assert best.pattern.startswith("ep_bau_") and all(word_count(c.text) <= 6 for c in cands)


# --- Grafik --------------------------------------------------------------------------
def test_isometric_render_and_build_frames(tmp_path, settings):
    city = {"residents": 13_400, "available_eur": 2_000_000,
            "buildings": [{"kind": "stadion", "name": "Stadion", "status": "built"}]}
    for overlay, data in ((None, {}), ("cost", {"name": "Freibad", "cost": 1_500_000}),
                          ("funding", {"have": 1, "need": 2, "label": "x"}),
                          ("vote", {"options": [{"name": "A", "cost": 1}, {"name": "B", "cost": 2}]}),
                          ("milestone", {"number": "14.000"}), ("keyword", {"keyword": "SEHR LANGES SCHLAGWORT " * 3})):
        img = render_city(tmp_path / f"{overlay}.png", 432, 768, city, highlight="freibad", overlay=overlay, data=data,
                          display_font=settings.font_path(settings.display_font),
                          bold_font=settings.font_path(settings.bold_font))
        assert img.size == (432, 768)
    d = render_build_frames(tmp_path / "b", 360, 640, city, "freibad", frames=10)
    frames = sorted(d.glob("f_*.png"))
    assert len(frames) == 10
    first, last = Image.open(frames[0]), Image.open(frames[-1])
    assert first.tobytes() != last.tobytes()  # Gebäude wächst
    assert len(set(slots())) == len(slots())


# --- Planung der Veröffentlichung --------------------------------------------------------
def test_schedule_and_publish_due(tmp_path):
    brain = BrainAgent(make_settings(tmp_path, allow_publishing=True), http_transport=wiki_transport({}))
    v = brain.memory.create_video("x")
    brain.memory.update_video(v["id"], status="approved")
    with pytest.raises(FactoryError):
        brain.schedule(v["id"], (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert brain.schedule(v["id"], future)["scheduled_for"]
    assert brain.due_for_publishing() == []
    brain.memory.update_video(v["id"], scheduled_for="2000-01-01T00:00+00:00")
    assert [x["id"] for x in brain.due_for_publishing()] == [v["id"]]
    assert brain.publish_due() == []  # Blocker: keine Videodatei, TikTok nicht verbunden -> nichts passiert
    draft = brain.memory.create_video("y")
    with pytest.raises(FactoryError):
        brain.schedule(draft["id"], future)  # nur geprüfte/freigegebene Videos


# --- Ende-zu-Ende ----------------------------------------------------------------------
@requires_windows_tts
def test_bobstadt_episode_end_to_end(tmp_path):
    brain = BrainAgent(make_settings(tmp_path, allow_publishing=True),
                       http_transport=wiki_transport({"Freibad": FREIBAD}))
    v = brain.produce(topic="Freibad")
    assert v["status"] == "ready", (v["error"], v["qc"])
    assert 60 <= v["duration_s"] <= 80
    assert v["episode"]["type"] == "bau" and v["category"] == "bobstadt"
    warn = next(c for c in v["qc"]["checks"] if c["name"] == "stadtstand_bestaetigt")
    assert warn["passed"] is False and warn["severity"] == "warning"
    assert "freibad" not in [b["kind"] for b in brain.memory.buildings("built")]
    brain.approve(v["id"])
    assert "freibad" in [b["kind"] for b in brain.memory.buildings("built")]
    from agents.tiktok_publisher import caption
    text = caption(brain.memory.get_video(v["id"]))
    assert "#bobstadt" in text and "Stadtzustand" not in text
    brain.publisher.client = FakeTikTok()
    assert brain.publish_due()[0]["status"] == "processing"
    assert Path(v["video_path"]).is_file()


def test_no_orphan_transition_without_facts(ctx, city, memory):
    ep = EpisodePlanner(city, memory, random.Random(1)).plan(wish="Freibad")
    from core.text import split_sentences
    w = ScriptWriterAgent(ctx)
    s = w.write_episode(ep, split_sentences(FREIBAD), HookCandidate(text="Freibad!", pattern="p"), 200)
    assert any(x.role == "turn" for x in s.segments)
    stripped = w.shorten(s, Idea(title=ep.title, angle="bau"), 999)
    assert not any(x.role in ("turn", "story") for x in stripped.segments)


class ScriptedVoice:
    """Simulierte Stimme: liefert nacheinander vorgegebene Gesamtdauern (stille WAVs, gleichmässige Wortzeiten)."""
    provider = "fake"

    def __init__(self, totals):
        self.totals, self.calls = list(totals), 0

    def synthesize_batch(self, items):
        from storage.models import VoiceClip
        from integrations.windows_tts import proportional_timings
        from video_engine.ffmpeg import run_ffmpeg
        total = self.totals[min(self.calls, len(self.totals) - 1)]
        self.calls += 1
        per = total / len(items)
        clips = []
        for text, wav in items:
            Path(wav).parent.mkdir(parents=True, exist_ok=True)
            run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-t", f"{per:.3f}", "-ac", "1",
                        "-c:a", "pcm_s16le", str(wav)])
            clips.append(VoiceClip(path=str(wav), duration_s=round(per, 3), provider="fake",
                                   words=proportional_timings(text, per)))
        return clips


@requires_windows_tts
def test_length_loop_falls_back_to_last_publishable_version(tmp_path):
    from agents.voice import VoiceAgent
    brain = BrainAgent(make_settings(tmp_path), http_transport=wiki_transport({"Freibad": FREIBAD}))
    voice = ScriptedVoice([77.0, 52.0, 50.0, 49.0])   # akzeptabel -> nach Kürzen zu kurz -> kein Material mehr
    brain.voice = VoiceAgent(brain.ctx, provider=voice)
    v = brain.produce(topic="Freibad")
    assert v["status"] in ("ready", "qc_failed"), v["error"]
    assert 75 <= v["duration_s"] <= 80 and v["revisions"] == 0  # Rückfall auf die akzeptable Rev. 0
    msgs = [e["message"] for e in brain.memory.events(video_id=v["id"])]
    assert any("Über Ideal" in m for m in msgs)
