import os
import shutil
from pathlib import Path

import pytest

from brain.budget import BudgetGuard
from brain.memory import Memory
from config import Settings
from storage.database import Database

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
IS_WINDOWS = os.name == "nt"
requires_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg/ffprobe nicht im PATH")
requires_windows_tts = pytest.mark.skipif(not (IS_WINDOWS and HAS_FFMPEG), reason="Windows-Sprachausgabe nicht verfügbar")

FIXTURES = Path(__file__).parent / "fixtures"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    """Isolierte Einstellungen: .env und Umgebungsschlüssel werden ignoriert, alles Kostenpflichtige ist aus."""
    base = dict(
        _env_file=None,
        data_dir=tmp_path / "data",
        assets_dir=tmp_path / "assets",
        video_width=360, video_height=640, fps=15,
        allow_paid_apis=False, allow_publishing=False,
        openai_api_key=None, elevenlabs_api_key=None, elevenlabs_voice_id=None,
        tiktok_client_key=None, tiktok_client_secret=None, tiktok_redirect_uri=None,
        meta_access_token=None, instagram_user_id=None, app_token=None,
        research_rss_feeds=[],
        content_mode="bobstadt",
    )
    base.update(overrides)
    s = Settings(**base)
    s.ensure_dirs()
    return s


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def db(settings) -> Database:
    return Database(settings.db_path)


@pytest.fixture
def memory(db) -> Memory:
    return Memory(db)


@pytest.fixture
def budget(settings, memory) -> BudgetGuard:
    return BudgetGuard(settings, memory)
