"""OpenAI – Bildgenerierung und optional Textgenerierung (KOSTENPFLICHTIG).

Dateiname bewusst nicht `openai.py`, damit das SDK-Paket `openai` nicht verdeckt wird.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from brain.budget import BudgetGuard
from config import Settings
from core.errors import ExternalApiError, NotConfiguredError


class OpenAIService:
    def __init__(self, settings: Settings, budget: BudgetGuard, client: Any | None = None):
        if not settings.openai_api_key and client is None:
            raise NotConfiguredError("OpenAI", ["OPENAI_API_KEY"])
        self.s, self.budget, self._client = settings, budget, client

    @property
    def client(self) -> Any:
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=self.s.openai_api_key.get_secret_value())  # type: ignore[union-attr]
        return self._client

    def generate_image(self, prompt: str, out_path: Path, size: str = "1024x1536") -> Path:
        """Erzeugt ein Hochformatbild. Ergebnisse werden nach Prompt-Hash zwischengespeichert (keine Doppelkosten)."""
        out_path = Path(out_path)
        cache = self.s.cache_dir / "images" / (hashlib.sha256(f"{self.s.openai_image_model}|{size}|{prompt}".encode())
                                               .hexdigest()[:24] + ".png")
        if not cache.exists():
            self.budget.authorize_paid_call("openai", "images.generate")
            try:
                resp = self.client.images.generate(model=self.s.openai_image_model, prompt=prompt, size=size,
                                                   quality=self.s.openai_image_quality, n=1)
            except Exception as exc:
                raise ExternalApiError("openai", type(exc).__name__ + ": " + str(exc)[:300]) from exc
            data = resp.data[0]
            if not getattr(data, "b64_json", None):
                raise ExternalApiError("openai", "Antwort enthält kein Bild (b64_json fehlt)")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(base64.b64decode(data.b64_json))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(cache.read_bytes())
        return out_path

    def complete_json(self, system: str, user: str, max_tokens: int = 1500) -> dict:
        self.budget.authorize_paid_call("openai", "chat.completions")
        try:
            resp = self.client.chat.completions.create(
                model=self.s.openai_text_model, response_format={"type": "json_object"}, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        except Exception as exc:
            raise ExternalApiError("openai", type(exc).__name__ + ": " + str(exc)[:300]) from exc
        content = resp.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ExternalApiError("openai", "Antwort ist kein gültiges JSON") from exc
