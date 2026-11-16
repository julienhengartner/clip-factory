"""SQLite-Datenbank: Schema, Migrationen, Verbindungen und Backups.

Bewusst ohne ORM: einfaches SQL, das sich später 1:1 nach PostgreSQL übertragen lässt.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

MIGRATIONS: list[str] = [
    # --- Version 1 -----------------------------------------------------------
    """
    CREATE TABLE research_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        url TEXT NOT NULL UNIQUE,
        source TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'allgemein',
        published_at TEXT,
        verified INTEGER NOT NULL DEFAULT 0,
        verification_note TEXT NOT NULL DEFAULT '',
        fetched_at TEXT NOT NULL
    );
    CREATE TABLE ideas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        angle TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'allgemein',
        research_ids TEXT NOT NULL DEFAULT '[]',
        score REAL NOT NULL DEFAULT 0,
        origin TEXT NOT NULL DEFAULT 'research',
        status TEXT NOT NULL DEFAULT 'new',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX idx_ideas_status ON ideas(status);
    CREATE TABLE videos (
        id TEXT PRIMARY KEY,
        idea_id INTEGER REFERENCES ideas(id),
        topic TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'allgemein',
        status TEXT NOT NULL,
        title TEXT,
        hook TEXT,
        hook_pattern TEXT,
        script_json TEXT,
        scenes_json TEXT,
        qc_json TEXT,
        video_path TEXT,
        thumbnail_path TEXT,
        duration_s REAL,
        words INTEGER,
        wpm REAL,
        voice_provider TEXT,
        image_provider TEXT,
        script_provider TEXT,
        revisions INTEGER NOT NULL DEFAULT 0,
        render_attempts INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        approved_at TEXT,
        published_at TEXT
    );
    CREATE INDEX idx_videos_status ON videos(status);
    CREATE TABLE hooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT REFERENCES videos(id) ON DELETE CASCADE,
        text TEXT NOT NULL,
        pattern TEXT NOT NULL,
        score REAL NOT NULL DEFAULT 0,
        chosen INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE publications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        platform TEXT NOT NULL,
        mode TEXT NOT NULL,
        publish_id TEXT,
        external_id TEXT,
        status TEXT NOT NULL,
        caption TEXT,
        privacy_level TEXT,
        message TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT REFERENCES videos(id) ON DELETE SET NULL,
        platform TEXT NOT NULL,
        external_id TEXT NOT NULL,
        views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER, saves INTEGER, reach INTEGER,
        collected_at TEXT NOT NULL
    );
    CREATE INDEX idx_perf_ext ON performance(platform, external_id);
    CREATE TABLE comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        external_id TEXT NOT NULL,
        media_id TEXT,
        text TEXT NOT NULL,
        author_hash TEXT,
        like_count INTEGER,
        category TEXT,
        sentiment REAL,
        keywords TEXT,
        commented_at TEXT,
        analyzed_at TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(platform, external_id)
    );
    CREATE TABLE follower_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        followers INTEGER,
        follows INTEGER,
        media_count INTEGER,
        collected_at TEXT NOT NULL
    );
    CREATE TABLE insights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        key TEXT NOT NULL,
        value_json TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(kind, key)
    );
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT,
        run_id INTEGER,
        level TEXT NOT NULL,
        source TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_events_video ON events(video_id);
    CREATE TABLE runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        status TEXT NOT NULL,
        summary_json TEXT,
        started_at TEXT NOT NULL,
        finished_at TEXT
    );
    CREATE TABLE settings_kv (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE api_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        operation TEXT NOT NULL,
        units REAL NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    CREATE TABLE oauth_states (
        state TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @property
    def schema_version(self) -> int:
        with self.connect() as c:
            return c.execute("PRAGMA user_version").fetchone()[0]

    def migrate(self) -> int:
        with self.connect() as c:
            version = c.execute("PRAGMA user_version").fetchone()[0]
            for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
                c.executescript(sql)
                c.execute(f"PRAGMA user_version = {i}")
        return self.schema_version

    # --- generische Helfer --------------------------------------------------
    def execute(self, sql: str, params: tuple | list = ()) -> int:
        """Führt aus und gibt lastrowid (INSERT) bzw. rowcount zurück."""
        with self.connect() as c:
            cur = c.execute(sql, params)
            return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount

    def query(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def query_one(self, sql: str, params: tuple | list = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: tuple | list = ()) -> Any:
        with self.connect() as c:
            row = c.execute(sql, params).fetchone()
        return row[0] if row else None

    # --- Backup -------------------------------------------------------------
    def backup(self, target_dir: Path, keep: int = 14) -> Path:
        """Konsistente Online-Sicherung über die SQLite-Backup-API; behält die letzten `keep` Dateien."""
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = target_dir / f"brain-{stamp}.db"
        n = 1
        while target.exists():
            target = target_dir / f"brain-{stamp}-{n}.db"
            n += 1
        src = sqlite3.connect(self.path)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        backups = sorted(target_dir.glob("brain-*.db"), key=lambda p: p.stat().st_mtime)
        for old in backups[:-keep] if keep > 0 else []:
            old.unlink(missing_ok=True)
        return target


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(value: str | None, default: Any = None) -> Any:
    return json.loads(value) if value else default
