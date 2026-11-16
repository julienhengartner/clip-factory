import json
import random

import pytest

from agents.base import AgentContext
from agents.comment_analysis import CommentAnalysisAgent, classify
from agents.hook import HookAgent, max_hook_words
from agents.quality_control import QualityControlAgent
from agents.script_writer import ScriptWriterAgent, rank_sentences
from agents.subtitles import build_cues
from agents.tiktok_publisher import TikTokPublisherAgent, caption, hashtags
from agents.video_director import VideoDirectorAgent
from brain.learning import LearningAgent
from brain.strategy import DEFAULT_STYLE, Strategy, categorize
from core.errors import FactoryError, InsufficientMaterialError
from core.text import split_sentences, word_count
from integrations.http import make_client
from integrations.token_store import TokenStore
from storage.models import HookCandidate, Idea, ResearchItem, Scene, Script, ScriptSegment, WordTiming
from tests.conftest import make_settings
from tests.fakes import LONG_TEXT, SHORT_TEXT
from video_engine.quality_check import MediaAnalysis, parse_analysis_log


@pytest.fixture
def ctx(settings, memory, budget):
    return AgentContext(settings=settings, memory=memory, budget=budget, http=make_client(settings),
                        tokens=TokenStore(settings.secrets_dir))


IDEA = Idea(id=1, title="Laufmaschine", angle="Erfindung", category="technik")


# --- Kommentare -----------------------------------------------------------------------------
@pytest.mark.parametrize("text,cat", [
    ("Wie lange hat Drais dafür gebraucht?", "frage"), ("Mach bitte mal ein Video über die Eisenbahn", "themenvorschlag"),
    ("Super Video, danke Bob! 😂", "lob"), ("Das stimmt nicht, total falsch", "kritik"),
    ("Folgt mir für gratis Follower www.spam.xy", "spam"), ("Ok", "sonstiges")])
def test_comment_classification(text, cat):
    assert classify(text)[0] == cat


def test_comment_requests_become_topics(ctx, memory):
    for i, t in enumerate(["Mach mal ein Video über Eisenbahn", "Bitte mehr über Eisenbahn und Dampflok",
                           "Was ist mit der Eisenbahn?", "Super!"]):
        memory.upsert_comment("instagram", f"c{i}", t, "m", f"user{i}", 0, None)
    agent = CommentAnalysisAgent(ctx)
    assert agent.analyze_pending()["themenvorschlag"] == 2
    assert agent.audience_requests()[0] == "Eisenbahn"
    assert agent.summary()["total"] == 4


# --- Hook --------------------------------------------------------------------------------
def test_hooks_respect_spoken_length(ctx):
    agent = HookAgent(ctx)
    for wpm in (120, 140, 165):
        for c in agent.candidates(IDEA, LONG_TEXT, wpm):
            assert word_count(c.text) <= max_hook_words(wpm)
    assert any(c.pattern == "zahl" and "1817" in c.text for c in agent.candidates(IDEA, LONG_TEXT, 150))


def test_hook_choice_follows_learning(ctx, memory):
    memory.set_insight("hook_pattern", "frage", {"mean": 3.0, "n": 20})
    best, _ = HookAgent(ctx).choose(IDEA, LONG_TEXT, 150, rng=random.Random(1))
    assert best.pattern == "frage"


# --- Skript & Länge ----------------------------------------------------------------------------
def test_script_meets_word_target_and_keeps_order(ctx):
    w = ScriptWriterAgent(ctx)
    material = split_sentences(LONG_TEXT)
    script = w.write(IDEA, material, HookCandidate(text="Laufmaschine – nicht, was du denkst.", pattern="kontrast"),
                     target_words=160, style=DEFAULT_STYLE)
    assert script.segments[0].role == "hook" and script.segments[-1].role == "cta"
    assert 160 <= script.word_count <= 160 + 30
    story = [s.text for s in script.segments if s.role == "story"]
    assert story == [s for s in material if s in story]  # Chronologie erhalten


def test_expand_and_shorten(ctx):
    w = ScriptWriterAgent(ctx)
    material = split_sentences(LONG_TEXT)
    hook = HookCandidate(text="Laufmaschine?", pattern="kontrast")
    short = w.write(IDEA, material, hook, target_words=90, style=DEFAULT_STYLE)
    longer = w.expand(short, IDEA, material, 40)
    assert longer.word_count >= short.word_count + 30 and longer.revision == 1
    shorter = w.shorten(longer, IDEA, 30)
    assert shorter.word_count < longer.word_count


def test_expand_never_pads_without_material(ctx):
    w = ScriptWriterAgent(ctx)
    material = split_sentences(SHORT_TEXT)
    script = w.write(IDEA, material, HookCandidate(text="Testweiler?", pattern="kontrast"), 400, DEFAULT_STYLE)
    with pytest.raises(InsufficientMaterialError):
        w.expand(script, IDEA, material, 100)


def test_rank_prefers_relevant_over_trivia():
    ranked = rank_sentences(["Seine Mutter starb früh und die Familie zog um.",
                             "Die Laufmaschine war die erste Erfindung dieser Art mit zwei Rädern."], "Laufmaschine")
    assert ranked[0].startswith("Die Laufmaschine")


def test_speech_rate_learning_drives_target(ctx, memory):
    w = ScriptWriterAgent(ctx)
    assert w.target_words("windows@2") == round(67.5 * 150 / 60)
    memory.set_insight("speech_rate", "windows@2", {"wpm": 130, "n": 3})
    assert w.target_words("windows@2") == round(67.5 * 130 / 60)


# --- Regie & Untertitel ------------------------------------------------------------------------
def test_director_scene_plan(ctx):
    script = Script(title="Laufmaschine", provider="offline", segments=[
        ScriptSegment(role="hook", text="Laufmaschine?"), ScriptSegment(role="intro", text="Hier ist Bob."),
        *[ScriptSegment(role="story", text=s) for s in split_sentences(LONG_TEXT)[:6]],
        ScriptSegment(role="cta", text="Schreib es in die Kommentare!")])
    scenes = VideoDirectorAgent(ctx).plan(script, DEFAULT_STYLE)
    assert scenes[0].role == "hook" and scenes[0].style == "hook" and scenes[-1].style == "cta"
    assert any(s.style == "number" and s.number == "1817" for s in scenes)
    assert all(word_count(s.text) <= 30 for s in scenes)


def test_cues_break_at_sentences_and_never_overlap():
    text = "Das ist gut. Und jetzt kommt mehr Text hier."
    ws = [WordTiming(word=w, start=i * 0.4, end=i * 0.4 + 0.35) for i, w in enumerate(
        ["Das", "ist", "gut", "Und", "jetzt", "kommt", "mehr", "Text", "hier"])]
    cues = build_cues([Scene(index=0, role="story", text=text, words=ws, duration_s=4.0, start_s=10.0)])
    assert cues[0].text == "Das ist gut" and cues[0].start == pytest.approx(10.0)
    assert all(a.end <= b.start + 1e-6 for a, b in zip(cues, cues[1:]))
    assert sum(len(c.words) for c in cues) == 9


# --- Strategie & Lernen -------------------------------------------------------------------------
def test_categorize_and_sensitive_filter():
    assert categorize("Karl Drais erfand die Laufmaschine") == "technik"
    assert categorize("Ein schwerer Anschlag forderte viele Opfer") == "sensibel"


def test_strategy_avoids_repeats_and_sensitive(settings, memory):
    strat = Strategy(settings, memory, random.Random(0))
    a = ResearchItem(title="Laufmaschine", summary=LONG_TEXT, url="https://de.wikipedia.org/wiki/L", source="wikipedia",
                     verified=True, category="technik")
    b = ResearchItem(title="Anschlag", summary="Anschlag mit Opfern", url="https://de.wikipedia.org/wiki/A",
                     source="wikipedia", verified=True, category="sensibel")
    c = ResearchItem(title="Ungeprüft", summary="x", url="https://evil.example/x", source="rss", verified=False)
    for it in (a, b, c):
        it.id = memory.add_research(it)
    ideas = strat.ideas_from_research([a, b, c])
    assert [i.title for i in ideas] == ["Laufmaschine"]
    assert strat.ideas_from_research([a]) == []  # schon bekannt
    v = memory.create_video("Laufmaschine Drais Mannheim")
    memory.update_video(v["id"], status="ready", title="Laufmaschine")
    strat.rescore()
    assert memory.list_ideas("new") == []  # nach Produktion -> Wiederholung verworfen


def test_style_profile_default_and_user_override(settings, memory):
    strat = Strategy(settings, memory)
    assert strat.style().source == "default_assumption" and strat.style().confirmed is False
    (settings.data_dir / "style_profile.json").write_text(json.dumps({"tone": "trocken"}), encoding="utf-8")
    assert strat.style().tone == "trocken" and strat.style().source == "user"


def test_learning_from_performance(memory):
    for i, (cat, pattern, views, likes, comments) in enumerate([
            ("technik", "frage", 10000, 900, 120), ("technik", "frage", 8000, 700, 90),
            ("technik", "frage", 9000, 800, 100), ("technik", "frage", 7000, 650, 80),
            ("politik", "bob", 1000, 10, 0), ("politik", "bob", 1200, 12, 1), ("politik", "bob", 900, 8, 0)]):
        v = memory.create_video(f"T{i}", category=cat)
        memory.update_video(v["id"], hook_pattern=pattern, duration_s=66, status="published")
        memory.add_performance("tiktok", f"x{i}", v["id"], views=views, likes=likes, comments=comments, shares=0)
    result = LearningAgent(memory).update()
    assert result["videos_with_data"] == 7
    cats = memory.insights("topic_category")
    assert cats["technik"]["mean"] > cats["politik"]["mean"]
    assert "politik" in result["recommendations"]["avoid_categories"]
    assert result["recommendations"]["best_hook_patterns"][0] == "frage"


def test_learning_without_data_invents_nothing(memory):
    assert LearningAgent(memory).update()["videos_with_data"] == 0
    assert memory.insights("topic_category") == {}


# --- Qualitätskontrolle ----------------------------------------------------------------------
def qc_inputs(duration=66.0, words_per_scene=12):
    scenes = []
    t = 0.0
    for i in range(6):
        ws = [WordTiming(word=f"w{k}", start=0.1 + k * 0.3, end=0.1 + k * 0.3 + 0.25) for k in range(words_per_scene)]
        d = duration / 6
        scenes.append(Scene(index=i, role="hook" if i == 0 else "story", text="Kurzer Hook" if i == 0 else "x " * 12,
                            words=ws[:2] if i == 0 else ws, duration_s=2.5 if i == 0 else d, start_s=t))
        t += d
    cues = build_cues(scenes)
    script = Script(title="t", provider="offline", sources=["https://de.wikipedia.org/wiki/T"],
                    segments=[ScriptSegment(role="story", text="wort " * 160)])
    return scenes, cues, script


def media(duration=66.0, **kw):
    base = dict(duration_s=duration, video_codec="h264", audio_codec="aac", width=360, height=640, fps=15.0,
                pix_fmt="yuv420p", audio_channels=2, integrated_lufs=-14.5, true_peak_dbfs=-2.0)
    base.update(kw)
    return MediaAnalysis(**base)


def test_qc_passes_good_video(ctx):
    scenes, cues, script = qc_inputs()
    report = QualityControlAgent(ctx).evaluate(media(), scenes, script, cues, True)
    assert report.passed, [c for c in report.errors]


@pytest.mark.parametrize("override,failed", [
    ({"duration": 59.5}, "laenge_minimum"), ({"duration": 81.0}, "laenge_maximum"),
    ({"silences": [(30.0, 2.4)]}, "keine_langen_pausen"), ({"freezes": [(10.0, 6.0)]}, "keine_standbilder"),
    ({"integrated_lufs": -25.0}, "lautheit"), ({"width": 1920, "height": 1080}, "format"),
    ({"blacks": [(0.0, 1.0)]}, "keine_schwarzbilder")])
def test_qc_detects_problems(ctx, override, failed):
    scenes, cues, script = qc_inputs()
    duration = override.pop("duration", 66.0)
    report = QualityControlAgent(ctx).evaluate(media(duration, **override), scenes, script, cues, True)
    assert not report.passed and failed in [c.name for c in report.errors]


def test_qc_requires_verified_sources_and_full_subtitles(ctx):
    scenes, cues, script = qc_inputs()
    report = QualityControlAgent(ctx).evaluate(media(), scenes, script, cues[:-3], False)
    names = [c.name for c in report.errors]
    assert "quellen_verifiziert" in names and "untertitel_vollstaendig" in names


def test_parse_ffmpeg_analysis_log():
    log = ("[silencedetect @ x] silence_start: 12.5\n[silencedetect @ x] silence_end: 13.4 | silence_duration: 0.9\n"
           "[blackdetect @ y] black_start:0 black_end:0.6 black_duration:0.6\n"
           "lavfi.freezedetect.freeze_start: 20.0\nlavfi.freezedetect.freeze_duration: 3.5\n"
           "[Parsed_ebur128_0 @ z] Summary:\n\n  Integrated loudness:\n    I:         -14.6 LUFS\n"
           "  True peak:\n    Peak:       -1.8 dBFS\n")
    p = parse_analysis_log(log)
    assert p["silences"] == [(12.5, 0.9)] and p["blacks"] == [(0.0, 0.6)] and p["freezes"] == [(20.0, 3.5)]
    assert p["integrated_lufs"] == -14.6 and p["true_peak_dbfs"] == -1.8


# --- Veröffentlichung --------------------------------------------------------------------------
def test_caption_and_hashtags():
    tags = hashtags("Laufmaschine", "technik", LONG_TEXT)
    assert tags[:3] == ["#bürgermeisterbob", "#wusstestdu", "#lernenmittiktok"] and "#erfindungen" in tags
    assert len(tags) <= 6
    video = {"id": "v", "topic": "Laufmaschine", "title": "Laufmaschine", "hook": "1817 – alles anders.",
             "category": "technik", "script": {"segments": [{"role": "cta", "text": "Hättest du das gewusst? Schreib!"}],
                                               "sources": ["https://de.wikipedia.org/wiki/L"]}}
    text = caption(video)
    assert "Hättest du das gewusst?" in text and "CC BY-SA" in text and len(text) <= 2200


class FakeTikTok:
    def __init__(self, connected=True, final_status="PUBLISH_COMPLETE"):
        self._connected, self.final_status, self.uploaded = connected, final_status, False

    def missing_requirements(self):
        return [] if self._connected else ["TIKTOK_CLIENT_KEY"]

    @property
    def connected(self):
        return self._connected

    def init_upload(self, path, mode, title="", privacy_level="SELF_ONLY"):
        return {"publish_id": "p1", "upload_url": "https://upload.example"}

    def upload_file(self, url, path):
        self.uploaded = True

    def fetch_status(self, publish_id):
        return {"status": self.final_status, "publicaly_available_post_id": [123]}


def ready_video(memory, tmp_path, duration_file=None):
    v = memory.create_video("Laufmaschine")
    path = duration_file or (tmp_path / "v.mp4")
    return memory.update_video(v["id"], status="approved", video_path=str(path), title="Laufmaschine",
                               script_json={"segments": [], "sources": []})


def test_publisher_blocks_without_permissions(ctx, memory, tmp_path):
    v = ready_video(memory, tmp_path)
    pub = TikTokPublisherAgent(ctx, client=FakeTikTok(connected=False))
    reasons = pub.blockers(v)
    assert any("BBOB_ALLOW_PUBLISHING" in r for r in reasons) and any("TIKTOK" in r for r in reasons)
    with pytest.raises(FactoryError):
        pub.publish(v)
