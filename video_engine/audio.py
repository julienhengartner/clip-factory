"""Audio: Sprachspuren zusammenfügen, lizenzierte Musik finden."""
from __future__ import annotations

from pathlib import Path

from config import Settings
from video_engine.ffmpeg import probe_duration, run_ffmpeg

MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")


def concat_wavs(wavs: list[Path], out_path: Path, settings: Settings) -> float:
    """Fügt Szenen-WAVs lückenlos aneinander (gleiches Format: 44,1 kHz mono PCM)."""
    out_path = Path(out_path)
    lst = out_path.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(w).resolve().as_posix()}'\n" for w in wavs), encoding="utf-8")
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le",
                str(out_path)], settings.ffmpeg_bin)
    lst.unlink(missing_ok=True)
    return probe_duration(out_path, settings.ffprobe_bin)


def licensed_tracks(music_dir: Path) -> list[Path]:
    """Nur Musikdateien mit einer Lizenzdatei daneben (<name>.license.txt) gelten als verwendbar."""
    if not music_dir.is_dir():
        return []
    return sorted(p for p in music_dir.iterdir()
                  if p.suffix.lower() in MUSIC_EXTS and p.with_name(p.stem + ".license.txt").is_file())


def pick_music(settings: Settings, seed: str) -> Path | None:
    if not settings.music_enabled:
        return None
    tracks = licensed_tracks(settings.music_dir)
    if not tracks:
        return None
    return tracks[sum(map(ord, seed)) % len(tracks)]
