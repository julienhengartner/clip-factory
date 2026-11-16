"""Voice Agent: deutsche Sprachaufnahmen je Szene + Messung der tatsächlichen Sprechgeschwindigkeit.

Anbieter: windows (kostenlos, lokal) oder elevenlabs (kostenpflichtig, natürlichere Stimme).
Die gemessene Rate (Wörter/Minute) wird gespeichert und vom Script Writer für die Längenplanung genutzt.
"""
from __future__ import annotations

from pathlib import Path

from agents.base import Agent, AgentContext
from core.text import word_count
from integrations.windows_tts import WindowsTTS
from storage.models import Scene


def make_voice_provider(ctx: AgentContext):
    if ctx.settings.voice_provider == "elevenlabs":
        from integrations.elevenlabs_api import ElevenLabsTTS
        return ElevenLabsTTS(ctx.settings, ctx.budget)
    return WindowsTTS(ctx.settings.windows_voice, ctx.settings.windows_voice_rate, ctx.settings.ffprobe_bin)


class VoiceAgent(Agent):
    name = "voice"

    def __init__(self, ctx: AgentContext, provider=None):
        super().__init__(ctx)
        self._provider = provider

    @property
    def provider(self):
        if self._provider is None:
            self._provider = make_voice_provider(self.ctx)
        return self._provider

    @property
    def provider_name(self) -> str:
        """Anbieter inkl. Einstellung – die gelernte Sprechrate gilt je Stimme/Geschwindigkeit."""
        name = getattr(self._provider, "provider", None) or self.s.voice_provider
        if name == "windows":
            return f"windows@{self.s.windows_voice_rate}"
        if name == "elevenlabs":
            return f"elevenlabs@{self.s.elevenlabs_voice_id or 'default'}"
        return name

    def synthesize(self, scenes: list[Scene], out_dir: Path) -> tuple[list[Scene], float, float]:
        """Gibt (Szenen mit Audio, Gesamtdauer, gemessene wpm) zurück."""
        out_dir.mkdir(parents=True, exist_ok=True)
        clips = self.provider.synthesize_batch([(sc.text, out_dir / f"scene_{sc.index:02d}.wav") for sc in scenes])
        updated, t = [], 0.0
        for sc, clip in zip(scenes, clips):
            updated.append(sc.model_copy(update={"audio_path": clip.path, "duration_s": clip.duration_s,
                                                 "words": clip.words, "start_s": round(t, 4)}))
            t += clip.duration_s
        words = sum(word_count(sc.text) for sc in scenes)
        wpm = round(words / t * 60, 1) if t > 0 else 0.0
        self.learn_rate(wpm)
        return updated, round(t, 3), wpm

    def learn_rate(self, wpm: float) -> None:
        """Gleitender Mittelwert der gemessenen Sprechrate pro Anbieter."""
        if wpm <= 0:
            return
        key = self.provider_name
        stats = self.memory.get_insight("speech_rate", key) or {"wpm": wpm, "n": 0}
        n = int(stats.get("n", 0))
        new = wpm if n == 0 else (stats["wpm"] * min(n, 9) + wpm) / (min(n, 9) + 1)
        self.memory.set_insight("speech_rate", key, {"wpm": round(new, 1), "n": n + 1, "last": wpm},
                                confidence=min(1.0, (n + 1) / 10))
