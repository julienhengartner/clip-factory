"""Domänenmodelle (Pydantic). Werden als JSON in SQLite abgelegt bzw. aus Tabellenzeilen erzeugt."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from core.text import normalize_space, word_count


class VideoStatus(str, Enum):
    PRODUCING = "producing"     # Pipeline läuft
    READY = "ready"             # Qualitätskontrolle bestanden, wartet auf Freigabe
    APPROVED = "approved"       # vom Menschen freigegeben
    PUBLISHING = "publishing"   # Upload läuft / wird von TikTok verarbeitet
    PUBLISHED = "published"     # von der TikTok-API bestätigt
    QC_FAILED = "qc_failed"     # Qualitätskontrolle nicht bestanden – wird nie veröffentlicht
    FAILED = "failed"           # technischer Fehler
    REJECTED = "rejected"       # vom Menschen abgelehnt


class ResearchItem(BaseModel):
    id: int | None = None
    title: str
    summary: str
    url: str
    source: str
    category: str = "allgemein"
    published_at: str | None = None
    verified: bool = False
    verification_note: str = ""


class Idea(BaseModel):
    id: int | None = None
    title: str
    angle: str
    category: str = "allgemein"
    research_ids: list[int] = Field(default_factory=list)
    score: float = 0.0
    origin: str = "research"    # research | comment | manual
    status: str = "new"         # new | used | rejected


class HookCandidate(BaseModel):
    text: str
    pattern: str
    score: float = 0.0


class ScriptSegment(BaseModel):
    role: str   # hook | intro | plot | story | turn | takeaway | cta  (story = austauschbares Faktenmaterial)
    text: str
    visual: str | None = None          # Bildvorgabe der Episode (city, build, cost, funding, vote, milestone …)
    data: dict = Field(default_factory=dict)


class Script(BaseModel):
    title: str
    segments: list[ScriptSegment]
    sources: list[str] = Field(default_factory=list)
    provider: str
    hook_pattern: str = ""
    revision: int = 0

    @property
    def full_text(self) -> str:
        return normalize_space(" ".join(s.text for s in self.segments))

    @property
    def word_count(self) -> int:
        return word_count(self.full_text)

    def segment(self, role: str) -> ScriptSegment | None:
        return next((s for s in self.segments if s.role == role), None)


class WordTiming(BaseModel):
    word: str
    start: float
    end: float


class Shot(BaseModel):
    """Ein Bildwechsel innerhalb einer Szene (verhindert lange Standbilder)."""
    start: float          # relativ zum Szenenbeginn
    duration: float
    motion: str
    variant: int = 0
    image_path: str | None = None
    frames_dir: str | None = None      # Einzelbild-Animation (z. B. Bau) statt Kamerafahrt


class Scene(BaseModel):
    index: int
    role: str
    text: str
    style: str = "keyword"   # hook | title | keyword | number | question | quote | cta | city | build | cost | funding | vote | milestone
    data: dict = Field(default_factory=dict)
    keyword: str = ""
    number: str | None = None
    palette: int = 0
    image_prompt: str = ""
    audio_path: str | None = None
    duration_s: float = 0.0
    start_s: float = 0.0
    words: list[WordTiming] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)


class VoiceClip(BaseModel):
    path: str
    duration_s: float
    words: list[WordTiming]
    provider: str


class SubtitleCue(BaseModel):
    start: float
    end: float
    words: list[WordTiming]

    @property
    def text(self) -> str:
        return " ".join(w.word for w in self.words)


class QCCheck(BaseModel):
    name: str
    passed: bool
    severity: str = "error"    # error | warning
    detail: str = ""
    value: float | str | None = None


class QCReport(BaseModel):
    checks: list[QCCheck]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks if c.severity == "error")

    @property
    def errors(self) -> list[QCCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    @property
    def warnings(self) -> list[QCCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]

    def get(self, name: str) -> QCCheck | None:
        return next((c for c in self.checks if c.name == name), None)


class StyleProfile(BaseModel):
    persona: str
    tone: str
    humor: str
    language: str
    narrative: str
    topics: list[str]
    audience: str
    visual_style: str
    editing_style: str
    recurring_elements: list[str]
    source: str = "default_assumption"   # default_assumption | user | analysis
    confirmed: bool = False


class PublishOutcome(BaseModel):
    platform: str = "tiktok"
    mode: str
    status: str
    publish_id: str | None = None
    message: str = ""
