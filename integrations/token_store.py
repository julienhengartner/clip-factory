"""Sichere Ablage von OAuth-Tokens.

Windows: Verschlüsselung mit der Windows Data Protection API (DPAPI, an das Benutzerkonto gebunden).
Linux (spätere Server-Migration): Datei mit Rechten 0600; für höhere Anforderungen auf einen
Secret-Manager umstellen. Tokens werden nie geloggt.
"""
from __future__ import annotations

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

from core.logging import get_logger

log = get_logger("token_store")


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _Blob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32  # type: ignore[attr-defined]
    src, out = _blob(data), _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out))  # 0x1 = UI_FORBIDDEN
    if not ok:
        raise OSError(f"DPAPI-Fehler {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


class TokenStore:
    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.use_dpapi = os.name == "nt"

    def _path(self, name: str) -> Path:
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_")
        return self.dir / f"{safe}.token"

    def save(self, name: str, data: dict) -> None:
        raw = json.dumps(data).encode("utf-8")
        payload = b"DPAPI1" + _dpapi(raw, True) if self.use_dpapi else b"PLAIN1" + raw
        path = self._path(name)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(payload)
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        tmp.replace(path)
        log.info("Token '%s' gespeichert (%s)", name, "DPAPI-verschlüsselt" if self.use_dpapi else "Dateirechte 0600")

    def load(self, name: str) -> dict | None:
        path = self._path(name)
        if not path.exists():
            return None
        payload = path.read_bytes()
        if payload.startswith(b"DPAPI1"):
            raw = _dpapi(payload[6:], False)
        elif payload.startswith(b"PLAIN1"):
            raw = payload[6:]
        else:
            raise ValueError(f"Unbekanntes Tokenformat in {path.name}")
        return json.loads(raw.decode("utf-8"))

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if path.exists():
            path.unlink()
            return True
        return False
