"""Episode format for Bobbington (data model + validation).

An episode is a list of shots. Each shot has a set, cast positions (named marks in the set), a camera
instruction, dialogue lines with actions/emotions, sound effects and optional on-screen text.
Lines marked `optional` may be dropped and `extensions` may be inserted by the length-fitting loop –
the length is always adjusted through the script, never with silence or still frames.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from bobbington.bible import CAST

ACTIONS = {"idle", "slam_desk", "raise_arms", "nod", "shake_head", "fold_arms", "point", "point_self", "thumbs_up",
           "stamp", "gossip_lean", "scratch_head", "polish_glass", "wring_hands", "lift_clipboard", "freeze", "shrug"}
EMOTIONS = {"neutral", "proud", "grand", "deadpan", "smug", "smarmy", "thrilled", "confused", "certain", "grumpy",
            "panicked", "shocked"}
CAMERA_TYPES = {"static", "wide", "two_shot", "close", "push_in"}
SETS = {"mayors_office", "council_chamber", "main_street", "pub", "title_card"}


class Line(BaseModel):
    speaker: str
    text: str
    action: str = "idle"
    emotion: str = "neutral"
    optional: bool = False
    pause_before: float = 0.18

    @model_validator(mode="after")
    def _check(self) -> "Line":
        if self.speaker not in CAST:
            raise ValueError(f"unknown speaker '{self.speaker}'")
        if self.action not in ACTIONS:
            raise ValueError(f"unknown action '{self.action}'")
        if self.emotion not in EMOTIONS:
            raise ValueError(f"unknown emotion '{self.emotion}'")
        return self


class Cue(BaseModel):
    name: str
    at: float | None = None             # seconds from shot start
    at_line_end: int | None = None      # or: after the end of line N of this shot
    volume: float = 1.0
    duration: float | None = None
    repeat: int = 1
    gap: float = 0.3


class Camera(BaseModel):
    type: str = "wide"
    target: str | None = None
    targets: list[str] = Field(default_factory=list)
    from_: float | None = Field(default=None, alias="from")
    to: float | None = None

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _check(self) -> "Camera":
        if self.type not in CAMERA_TYPES:
            raise ValueError(f"unknown camera type '{self.type}'")
        return self


class Shot(BaseModel):
    id: str
    set: str
    cast: dict[str, str] = Field(default_factory=dict)
    camera: Camera = Field(default_factory=Camera)
    lines: list[Line] = Field(default_factory=list)
    sfx: list[Cue] = Field(default_factory=list)
    music: Cue | None = None
    on_screen: dict[str, str] = Field(default_factory=dict)
    duration: float | None = None       # only for shots without dialogue (title card)

    @model_validator(mode="after")
    def _check(self) -> "Shot":
        if self.set not in SETS:
            raise ValueError(f"unknown set '{self.set}'")
        for line in self.lines:
            if line.speaker not in self.cast:
                raise ValueError(f"shot {self.id}: speaker {line.speaker} is not placed in the shot")
        if not self.lines and not self.duration:
            raise ValueError(f"shot {self.id}: needs lines or a fixed duration")
        return self


class Extension(BaseModel):
    after_shot: str
    speaker: str
    text: str
    action: str = "idle"
    emotion: str = "neutral"


class Episode(BaseModel):
    id: str
    title: str
    logline: str
    structure: dict[str, str]
    running_gags: list[str] = Field(default_factory=list)
    sim_effects: list[dict] = Field(default_factory=list)
    shots: list[Shot]
    extensions: list[Extension] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "Episode":
        missing = {"beginning", "conflict", "escalation", "twist", "punchline"} - set(self.structure)
        if missing:
            raise ValueError(f"structure incomplete: {sorted(missing)}")
        speakers = {line.speaker for s in self.shots for line in s.lines}
        if "winston" not in speakers:
            raise ValueError("Winston must appear in every episode")
        if len(speakers) < 2:
            raise ValueError("at least two cast members must speak")
        ids = [s.id for s in self.shots]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate shot ids")
        for ext in self.extensions:
            if ext.after_shot not in ids:
                raise ValueError(f"extension refers to unknown shot {ext.after_shot}")
        return self

    @property
    def word_count(self) -> int:
        return sum(len(line.text.split()) for s in self.shots for line in s.lines)


def load_episode(path: str | Path) -> Episode:
    return Episode.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
