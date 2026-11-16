import logging

import pytest

from config import Settings
from core.logging import RedactingFilter, redact
from core.text import (clean_research_text, first_number, keywords, similarity, split_sentences, word_count,
                       words_for_duration)
from video_engine.duration import LengthVerdict, evaluate_length
from tests.conftest import make_settings


def test_split_sentences_german():
    text = "Am 12. Juni 1817 fuhr Karl Drais los. Er kam z. B. bis Schwetzingen! War das schnell? Ja."
    assert split_sentences(text) == ["Am 12. Juni 1817 fuhr Karl Drais los.", "Er kam z. B. bis Schwetzingen!",
                                     "War das schnell?", "Ja."]


def test_clean_and_count():
    assert clean_research_text("Karl Drais (* 1785; † 1851) war ein Erfinder[1].") == "Karl Drais war ein Erfinder."
    assert word_count("Die Laufmaschine – ein Zweirad, 1817 erfunden.") == 6
    assert words_for_duration(60, 150) == 150


def test_keywords_and_similarity():
    kws = keywords("Die Laufmaschine von Drais. Die Laufmaschine hatte zwei Räder.", 2)
    assert kws[0] == "Laufmaschine"
    assert similarity("Laufmaschine Drais Mannheim", "Drais Laufmaschine Erfindung") > 0.4
    assert similarity("Laufmaschine", "Mondlandung") == 0
    assert first_number("Im Jahr 1817 und 3 Räder") == "1817"


@pytest.mark.parametrize("seconds,verdict", [
    (59.9, LengthVerdict.TOO_SHORT), (60, LengthVerdict.IDEAL), (75, LengthVerdict.IDEAL),
    (77, LengthVerdict.ACCEPTABLE), (80, LengthVerdict.ACCEPTABLE), (80.5, LengthVerdict.TOO_LONG),
    (float("nan"), LengthVerdict.INVALID), (-1, LengthVerdict.INVALID)])
def test_length_policy(settings, seconds, verdict):
    r = evaluate_length(seconds, settings)
    assert r.verdict == verdict
    assert r.publishable == (verdict in (LengthVerdict.IDEAL, LengthVerdict.ACCEPTABLE))


def test_settings_validation(tmp_path):
    with pytest.raises(ValueError):
        make_settings(tmp_path, min_duration_s=70, ideal_max_duration_s=65)
    s = make_settings(tmp_path)
    assert s.target_duration_s == 67.5
    assert "sk-geheim" not in repr(make_settings(tmp_path, openai_api_key="sk-geheim123456"))


def test_redaction():
    text = 'Authorization: Bearer abc.def-123 key sk-ABCDEFGHIJKLMNOP access_token=xyz123&x=1 "client_secret": "s3cr3t"'
    out = redact(text, ["supersecretvalue"])
    for leaked in ("abc.def-123", "sk-ABCDEFGHIJKLMNOP", "xyz123", "s3cr3t"):
        assert leaked not in out
    assert redact("Token supersecretvalue", ["supersecretvalue"]) == "Token ***"


def test_redacting_filter_on_logger():
    rec = logging.LogRecord("bbob.t", logging.INFO, __file__, 1, "Schlüssel %s", ("meinGeheimnis",), None)
    RedactingFilter(["meinGeheimnis"]).filter(rec)
    assert rec.getMessage() == "Schlüssel ***"


def test_empty_env_values_count_as_unset(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=\nTIKTOK_CLIENT_KEY=   \nBBOB_ALLOW_PAID_APIS=false\n", encoding="utf-8")
    s = Settings(_env_file=env, data_dir=tmp_path)
    assert s.openai_api_key is None and s.tiktok_client_key is None
