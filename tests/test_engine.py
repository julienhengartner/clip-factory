from pathlib import Path

import pytest
from PIL import Image

from integrations.windows_tts import proportional_timings, word_timings_from_sapi
from storage.models import Scene, SubtitleCue, WordTiming
from tests.conftest import requires_ffmpeg, requires_windows_tts
from video_engine.audio import licensed_tracks, pick_music
from video_engine.quality_check import analyze
from video_engine.renderer import VideoRenderer
from video_engine.scenes import plan_shots
from video_engine.subtitles import write_ass, write_srt
from video_engine.visuals import oversized, render_background
from tests.conftest import make_settings


def test_sapi_timing_correction():
    text = "Wusstest du, dass Bob spricht?"
    # SAPI-Rohwerte (Basis 16 kHz) für eine 44,1-kHz-Datei
    events = [{"t": 137.0, "pos": 0, "len": 8}, {"t": 805.0, "pos": 9, "len": 2}, {"t": 1859.0, "pos": 13, "len": 4},
              {"t": 2148.0, "pos": 18, "len": 3}, {"t": 2600.0, "pos": 22, "len": 7}]
    ws = word_timings_from_sapi(text, events, duration_s=1.5)
    assert [w.word for w in ws] == ["Wusstest", "du", "dass", "Bob", "spricht"]
    assert ws[2].start == pytest.approx(1.859 * 16000 / 44100, abs=1e-3)
    assert all(a.start <= b.start for a, b in zip(ws, ws[1:]))


def test_sapi_implausible_timings_fall_back():
    ws = word_timings_from_sapi("Eins zwei drei", [{"t": 99999, "pos": 0, "len": 4}], duration_s=1.0)
    assert [w.word for w in ws] == ["Eins", "zwei", "drei"] and ws[-1].end <= 1.0
    assert proportional_timings("", 2.0) == []


def test_plan_shots_frame_exact():
    scenes = [Scene(index=i, role="story", text="x", duration_s=d) for i, d in enumerate([3.37, 9.81, 5.5])]
    planned = plan_shots(scenes, fps=30, max_shot_s=4.5)
    assert [len(s.shots) for s in planned] == [1, 3, 2]
    frames = sum(round(sh.duration * 30) for s in planned for sh in s.shots)
    assert frames == round(sum(s.duration_s for s in scenes) * 30)
    assert all(sh.duration <= 4.5 + 1 / 30 for s in planned for sh in s.shots)
    motions = [sh.motion for s in planned for sh in s.shots]
    assert all(a != b for a, b in zip(motions, motions[1:]))  # Bewegung wechselt immer


def test_visuals_all_styles(tmp_path, settings):
    for style in ("hook", "title", "keyword", "number", "question", "quote", "cta"):
        p = render_background(tmp_path / f"{style}.png", 360, 640, style=style, keyword="Laufmaschine", number="1817",
                              title="Laufmaschine", display_font=settings.font_path(settings.display_font),
                              bold_font=settings.font_path(settings.bold_font))
        assert Image.open(p).size == oversized(360, 640)


def test_subtitle_files(tmp_path, settings):
    cues = [SubtitleCue(start=0.1, end=0.9, words=[WordTiming(word="Hallo", start=0.1, end=0.5),
                                                    WordTiming(word="{Welt}", start=0.5, end=0.9)])]
    ass = write_ass(cues, tmp_path / "s.ass", settings).read_text(encoding="utf-8")
    assert "PlayResX: 360" in ass and "{\\k40}HALLO {\\k40}(WELT)" in ass
    srt = write_srt(cues, tmp_path / "s.srt").read_text(encoding="utf-8")
    assert "00:00:00,100 --> 00:00:00,900" in srt


def test_music_only_with_license(tmp_path):
    s = make_settings(tmp_path, music_enabled=True)
    (s.music_dir / "song.mp3").write_bytes(b"x")
    assert pick_music(s, "a") is None
    (s.music_dir / "song.license.txt").write_text("CC0", encoding="utf-8")
    assert licensed_tracks(s.music_dir) == [s.music_dir / "song.mp3"]
    assert pick_music(make_settings(tmp_path, music_enabled=False), "a") is None


@requires_windows_tts
def test_render_and_analyze_real_clip(tmp_path, settings):
    from integrations.windows_tts import WindowsTTS
    texts = ["Hallo, hier ist Bob.", "Heute geht es um die Laufmaschine aus dem Jahr 1817."]
    clips = WindowsTTS(settings.windows_voice, 2).synthesize_batch([(t, tmp_path / f"{i}.wav") for i, t in enumerate(texts)])
    scenes = [Scene(index=i, role="story", text=t, style="number" if i else "hook", keyword="Bob", number="1817",
                    duration_s=c.duration_s, audio_path=c.path, words=c.words) for i, (t, c) in enumerate(zip(texts, clips))]
    scenes = plan_shots(scenes, settings.fps, settings.max_shot_s)
    for sc in scenes:
        for sh in sc.shots:
            sh.image_path = str(render_background(tmp_path / f"i{sc.index}{sh.variant}.png", 360, 640, style=sc.style,
                                                  keyword=sc.keyword, number=sc.number))
    from video_engine.audio import concat_wavs
    total = concat_wavs([Path(c.path) for c in clips], tmp_path / "voice.wav", settings)
    out = VideoRenderer(settings).render(scenes, tmp_path / "voice.wav", None, tmp_path / "out.mp4")
    a = analyze(out, settings)
    assert abs(a.duration_s - total) < 0.1
    assert (a.width, a.height, a.video_codec, a.audio_codec) == (360, 640, "h264", "aac")
    assert a.longest_freeze_s < 2.0 and a.integrated_lufs is not None
