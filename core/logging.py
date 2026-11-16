"""Logging mit automatischer Schwärzung von Zugangsdaten."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),                                  # OpenAI-artige Schlüssel
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-~+/=]+"),
    re.compile(r"(?i)((?:access|refresh)_token|client_secret|api[_-]?key|xi-api-key)([\"'=:\s]+)[^\s\"'&,}]+"),
]

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def redact(text: str, secrets: list[str] | tuple[str, ...] = ()) -> str:
    for s in secrets:
        if s and len(s) >= 4:
            text = text.replace(s, "***")
    text = _PATTERNS[0].sub("***", text)
    text = _PATTERNS[1].sub(r"\1***", text)
    text = _PATTERNS[2].sub(r"\1\2***", text)
    return text


class RedactingFilter(logging.Filter):
    def __init__(self, secrets: list[str] | None = None):
        super().__init__()
        self.secrets = list(secrets or [])

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover
            return True
        record.msg = redact(msg, self.secrets)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text, self.secrets)
        return True


_configured = False


def setup_logging(logs_dir: Path, secrets: list[str] | None = None, level: int = logging.INFO) -> None:
    global _configured
    root = logging.getLogger("bbob")
    root.setLevel(level)
    filt = RedactingFilter(secrets)
    if _configured:
        for h in root.handlers:
            for f in list(h.filters):
                if isinstance(f, RedactingFilter):
                    f.secrets = list(secrets or [])
        return
    logs_dir.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(logs_dir / "factory.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    sh = logging.StreamHandler()
    for h in (fh, sh):
        h.setFormatter(logging.Formatter(_FORMAT))
        h.addFilter(filt)
        root.addHandler(h)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"bbob.{name}")
