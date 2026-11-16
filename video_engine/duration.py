"""Längenrichtlinie (absolute Priorität).

  < 60 s          -> TOO_SHORT  (nie veröffentlichen, Skript erweitern)
  60 – 75 s       -> IDEAL
  75 – 80 s       -> ACCEPTABLE (veröffentlichbar, Warnung)
  > 80 s          -> TOO_LONG   (Skript kürzen)
"""
from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel

from config import Settings


class LengthVerdict(str, Enum):
    TOO_SHORT = "too_short"
    IDEAL = "ideal"
    ACCEPTABLE = "acceptable"
    TOO_LONG = "too_long"
    INVALID = "invalid"


class LengthResult(BaseModel):
    seconds: float
    verdict: LengthVerdict
    message: str
    missing_s: float = 0.0   # wie viel fehlt bis zum Minimum (inkl. Sicherheitsmarge)
    excess_s: float = 0.0    # wie viel über dem Idealmaximum

    @property
    def publishable(self) -> bool:
        return self.verdict in (LengthVerdict.IDEAL, LengthVerdict.ACCEPTABLE)


SAFETY_MARGIN_S = 1.5  # Puffer, damit Rundungen/Encoding nicht knapp unter 60 s fallen


def evaluate_length(seconds: float, settings: Settings) -> LengthResult:
    lo, ideal_hi, hard_hi = settings.min_duration_s, settings.ideal_max_duration_s, settings.hard_max_duration_s
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        s = float("nan")
    if math.isnan(s) or math.isinf(s) or s <= 0:
        return LengthResult(seconds=0.0, verdict=LengthVerdict.INVALID, message=f"Ungültige Dauer: {seconds!r}")
    s = round(s, 3)
    if s < lo:
        return LengthResult(seconds=s, verdict=LengthVerdict.TOO_SHORT,
                            missing_s=round(lo - s + SAFETY_MARGIN_S, 2),
                            message=f"Zu kurz: {s:.2f} s – Minimum {lo:.0f} s, es fehlen {lo - s:.2f} s")
    if s <= ideal_hi:
        return LengthResult(seconds=s, verdict=LengthVerdict.IDEAL, message=f"Ideal: {s:.2f} s ({lo:.0f}–{ideal_hi:.0f} s)")
    if s <= hard_hi:
        return LengthResult(seconds=s, verdict=LengthVerdict.ACCEPTABLE, excess_s=round(s - ideal_hi, 2),
                            message=f"Akzeptabel: {s:.2f} s (über Ideal {ideal_hi:.0f} s, unter Maximum {hard_hi:.0f} s)")
    return LengthResult(seconds=s, verdict=LengthVerdict.TOO_LONG, excess_s=round(s - ideal_hi, 2),
                        message=f"Zu lang: {s:.2f} s – Maximum {hard_hi:.0f} s")
