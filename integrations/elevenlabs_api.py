"""ElevenLabs – deutsche Sprachausgabe mit Zeichen-Zeitstempeln (KOSTENPFLICHTIG).

Jeder Aufruf läuft über BudgetGuard (Freigabe + Tageslimit). Ohne Schlüssel/Stimme: NotConfiguredError.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from brain.budget import BudgetGuard
from config import Settings
from core.errors import ExternalApiError, NotConfiguredError
from storage.models import VoiceClip, WordTiming
from video_engine.ffmpeg import probe_duration, run_ffmpeg


def words_from_alignment(characters: list[str], starts: list[float], ends: list[float]) -> list[WordTiming]:
    out, buf, w_start, w_end = [], "", None, 0.0
    for ch, st, en in zip(characters, starts, ends):
        if ch.isspace():
            if buf.strip():
                out.append(WordTiming(word=buf.strip(), start=w_start, end=w_end))
            buf, w_start = "", None
            continue
        if w_start is None:
            w_start = st
        buf += ch
        w_end = en
    if buf.strip():
        out.append(WordTiming(word=buf.strip(), start=w_start or 0.0, end=w_end))
    # Satzzeichen am Wortrand entfernen (Untertitel zeigen sie trotzdem über den Originaltext)
    return [WordTiming(word=w.word.strip(".,!?;:\"„“»«()"), start=round(w.start, 3), end=round(w.end, 3))
            for w in out if w.word.strip(".,!?;:\"„“»«()")]


class ElevenLabsTTS:
    provider = "elevenlabs"

    def __init__(self, settings: Settings, budget: BudgetGuard, client: Any | None = None):
        self.s, self.budget = settings, budget
        missing = []
        if not settings.elevenlabs_api_key:
            missing.append("ELEVENLABS_API_KEY")
        if not settings.elevenlabs_voice_id:
            missing.append("ELEVENLABS_VOICE_ID")
        if missing and client is None:
            raise NotConfiguredError("ElevenLabs", missing)
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            from elevenlabs.client import ElevenLabs
            self._client = ElevenLabs(api_key=self.s.elevenlabs_api_key.get_secret_value())  # type: ignore[union-attr]
        return self._client

    def synthesize_batch(self, items: list[tuple[str, Path]]) -> list[VoiceClip]:
        clips, prev_text = [], None
        for text, wav in items:
            self.budget.authorize_paid_call("elevenlabs", "text_to_speech", units=len(text))
            try:
                resp = self.client.text_to_speech.convert_with_timestamps(
                    self.s.elevenlabs_voice_id, text=text, model_id=self.s.elevenlabs_model,
                    output_format="mp3_44100_128", language_code="de", previous_text=prev_text)
            except Exception as exc:  # SDK-Fehler vereinheitlichen, ohne Schlüssel auszugeben
                raise ExternalApiError("elevenlabs", type(exc).__name__ + ": " + str(exc)[:300]) from exc
            wav = Path(wav)
            wav.parent.mkdir(parents=True, exist_ok=True)
            mp3 = wav.with_suffix(".mp3")
            mp3.write_bytes(base64.b64decode(resp.audio_base_64))
            run_ffmpeg(["-i", str(mp3), "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], self.s.ffmpeg_bin)
            mp3.unlink(missing_ok=True)
            al = resp.alignment
            words = words_from_alignment(al.characters, al.character_start_times_seconds,
                                         al.character_end_times_seconds) if al else []
            clips.append(VoiceClip(path=str(wav), duration_s=round(probe_duration(wav, self.s.ffprobe_bin), 3),
                                   words=words, provider=self.provider))
            prev_text = text
        return clips
