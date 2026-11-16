"""Zentrale Konfiguration.

Quellen (in dieser Reihenfolge): Konstruktor-Argumente > Umgebungsvariablen > .env-Datei > Standardwerte.
Projektspezifische Variablen beginnen mit BBOB_, Zugangsdaten tragen die üblichen Namen (OPENAI_API_KEY ...).
Alle Geheimnisse sind SecretStr und erscheinen dadurch nie im Klartext in Logs oder repr().
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent


def _alias(name: str) -> AliasChoices:
    return AliasChoices(name, name.lower())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BBOB_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- Ablage ---------------------------------------------------------
    data_dir: Path = PROJECT_ROOT / "data"
    assets_dir: Path = PROJECT_ROOT / "assets"

    # --- FFmpeg / Schriften ---------------------------------------------
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    fonts_dir: Path = Path("C:/Windows/Fonts")
    display_font: str = "impact.ttf"
    bold_font: str = "arialbd.ttf"
    subtitle_font_name: str = "Arial"

    # --- Videolänge (absolute Priorität) --------------------------------
    min_duration_s: float = 60.0         # darunter wird NIE veröffentlicht
    ideal_max_duration_s: float = 75.0   # Idealbereich 60–75 s
    hard_max_duration_s: float = 80.0    # maximale Standardlänge
    wpm_min: float = 130.0
    wpm_max: float = 165.0

    # --- Videoformat ----------------------------------------------------
    video_width: int = 1080
    video_height: int = 1920
    fps: int = 30
    max_shot_s: float = 4.5              # spätestens dann wechselt das Bild

    # --- Grenzen gegen Endlosschleifen und Kosten -----------------------
    max_script_revisions: int = 3
    max_render_attempts: int = 2
    max_videos_per_day: int = 1
    max_paid_calls_per_day: int = 40
    http_retries: int = 2

    # --- Inhalt ---------------------------------------------------------
    # bobstadt: Episoden der Community-Aufbausimulation (wie der Instagram-Kanal)
    # wissen:   Wissensvideos aus recherchierten Themen
    content_mode: Literal["bobstadt", "wissen"] = "bobstadt"

    # --- Bobbington (3D-Serie) ---------------------------------------------
    blender_bin: Path = Path("C:/Tools/blender-4.5.16-windows-x64/blender.exe")
    piper_voices_dir: Path = Path("C:/Tools/piper-voices")
    animation_fps: int = 24

    # --- Anbieter -------------------------------------------------------
    voice_provider: Literal["windows", "elevenlabs"] = "windows"
    windows_voice: str = "Microsoft Hedda Desktop"
    windows_voice_rate: int = 2          # -10 … 10; 2 ≈ 157 wpm mit Hedda (gemessen)
    image_provider: Literal["procedural", "openai"] = "procedural"
    llm_provider: Literal["offline", "openai"] = "offline"

    # --- Sicherheitsschalter (standardmässig AUS) -----------------------
    allow_paid_apis: bool = False
    allow_publishing: bool = False
    tiktok_publish_mode: Literal["inbox", "direct"] = "inbox"
    tiktok_privacy_level: str = "SELF_ONLY"
    music_enabled: bool = False

    # --- Recherche ------------------------------------------------------
    research_language: str = "de"
    research_rss_feeds: list[str] = Field(default_factory=list)
    trusted_domains: list[str] = Field(default_factory=lambda: [
        "wikipedia.org", "wikimedia.org", "tagesschau.de", "zdf.de", "srf.ch", "orf.at",
        "admin.ch", "bund.de", "destatis.de", "bfs.admin.ch", "dlf.de", "deutschlandfunk.de",
    ])
    # Wikimedia verlangt eine Kontaktangabe (URL oder E-Mail) im User-Agent, sonst HTTP 403.
    http_user_agent: str = "BuergermeisterBobVideoFactory/0.2 (https://www.instagram.com/buergermeisterbob/) httpx"

    # --- Zugangsdaten (nur über .env / Umgebung) ------------------------
    openai_api_key: SecretStr | None = Field(default=None, validation_alias=_alias("OPENAI_API_KEY"))
    openai_text_model: str = "gpt-4o-mini"
    openai_image_model: str = "gpt-image-2"
    openai_image_quality: str = "medium"
    elevenlabs_api_key: SecretStr | None = Field(default=None, validation_alias=_alias("ELEVENLABS_API_KEY"))
    elevenlabs_voice_id: str | None = Field(default=None, validation_alias=_alias("ELEVENLABS_VOICE_ID"))
    elevenlabs_model: str = "eleven_multilingual_v2"
    tiktok_client_key: str | None = Field(default=None, validation_alias=_alias("TIKTOK_CLIENT_KEY"))
    tiktok_client_secret: SecretStr | None = Field(default=None, validation_alias=_alias("TIKTOK_CLIENT_SECRET"))
    tiktok_redirect_uri: str | None = Field(default=None, validation_alias=_alias("TIKTOK_REDIRECT_URI"))
    meta_access_token: SecretStr | None = Field(default=None, validation_alias=_alias("META_ACCESS_TOKEN"))
    instagram_user_id: str | None = Field(default=None, validation_alias=_alias("INSTAGRAM_USER_ID"))
    meta_graph_base: str = "https://graph.facebook.com/v21.0"

    # --- Bedienoberfläche -----------------------------------------------
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_token: SecretStr | None = None   # BBOB_APP_TOKEN – Pflicht, wenn nicht nur lokal gebunden

    backups_keep: int = 14

    @field_validator("openai_api_key", "elevenlabs_api_key", "elevenlabs_voice_id", "tiktok_client_key",
                     "tiktok_client_secret", "tiktok_redirect_uri", "meta_access_token", "instagram_user_id",
                     "app_token", mode="before")
    @classmethod
    def _empty_is_none(cls, v):
        """Leere Einträge aus einer kopierten .env.example gelten als 'nicht gesetzt'."""
        if v is None:
            return None
        raw = v.get_secret_value() if isinstance(v, SecretStr) else str(v)
        return None if not raw.strip() else v

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if not (0 < self.min_duration_s <= self.ideal_max_duration_s <= self.hard_max_duration_s):
            raise ValueError("Es muss gelten: 0 < min_duration_s <= ideal_max_duration_s <= hard_max_duration_s")
        if self.video_width % 2 or self.video_height % 2:
            raise ValueError("Videobreite und -höhe müssen gerade sein")
        if not (0 < self.wpm_min < self.wpm_max):
            raise ValueError("wpm_min < wpm_max erforderlich")
        return self

    # --- abgeleitete Pfade ----------------------------------------------
    @property
    def db_path(self) -> Path:
        return self.data_dir / "brain.db"

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def secrets_dir(self) -> Path:
        return self.data_dir / "secrets"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def music_dir(self) -> Path:
        return self.assets_dir / "music"

    @property
    def target_duration_s(self) -> float:
        """Zielwert für die Planung: Mitte des Idealbereichs."""
        return round((self.min_duration_s + self.ideal_max_duration_s) / 2, 1)

    def font_path(self, name: str) -> Path:
        return self.fonts_dir / name

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.videos_dir, self.logs_dir, self.backups_dir, self.secrets_dir,
                  self.cache_dir, self.music_dir):
            d.mkdir(parents=True, exist_ok=True)

    def secret_values(self) -> list[str]:
        """Alle gesetzten Geheimnisse – für den Log-Filter."""
        vals = []
        for name in ("openai_api_key", "elevenlabs_api_key", "tiktok_client_secret", "meta_access_token", "app_token"):
            v = getattr(self, name)
            if v is not None and v.get_secret_value():
                vals.append(v.get_secret_value())
        return vals


def get_settings(**overrides) -> Settings:
    return Settings(**overrides)
