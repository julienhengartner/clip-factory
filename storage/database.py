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
    # --- Version 2: Bobstadt (Stadtzustand, Community-Vorschläge), Episoden, geplante Veröffentlichung ---
    """
    ALTER TABLE videos ADD COLUMN episode_json TEXT;
    ALTER TABLE videos ADD COLUMN scheduled_for TEXT;
    CREATE TABLE city_buildings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        name TEXT NOT NULL,
        cost_eur INTEGER NOT NULL,
        status TEXT NOT NULL,              -- planned | built
        origin TEXT NOT NULL,              -- seed | community | bob
        confirmed INTEGER NOT NULL DEFAULT 1,
        video_id TEXT,
        note TEXT,
        created_at TEXT NOT NULL,
        built_at TEXT
    );
    CREATE TABLE proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,                -- building | name
        value TEXT NOT NULL,
        voters TEXT NOT NULL DEFAULT '[]', -- Hashes der Kommentar-Autoren (eine Stimme pro Person)
        status TEXT NOT NULL DEFAULT 'open',
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        UNIQUE(kind, value)
    );
    """,
    # --- Version 3: Bobbington city simulation (fictional; never linked to real followers) ---------------
    """
    CREATE TABLE sim_state (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
    CREATE TABLE sim_departments (
        name TEXT PRIMARY KEY, head TEXT, annual_budget_pence INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE sim_ledger (                -- append-only; every pound is traceable
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sim_day INTEGER NOT NULL,
        department TEXT NOT NULL REFERENCES sim_departments(name),
        kind TEXT NOT NULL CHECK (kind IN ('opening', 'revenue', 'expense')),
        amount_pence INTEGER NOT NULL CHECK (amount_pence > 0),
        balance_after_pence INTEGER NOT NULL,
        description TEXT NOT NULL,
        reference TEXT,                       -- e.g. episode:s01e01, project:3
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_ledger_ref ON sim_ledger(reference);
    CREATE TABLE sim_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, department TEXT NOT NULL, budget_pence INTEGER NOT NULL,
        spent_pence INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, note TEXT,
        started_day INTEGER, completed_day INTEGER, episode_id TEXT
    );
    CREATE TABLE sim_businesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, owner TEXT, kind TEXT, weekly_rates_pence INTEGER NOT NULL, status TEXT NOT NULL
    );
    CREATE TABLE sim_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sim_day INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, description TEXT, episode_id TEXT
    );
    CREATE TABLE sim_complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sim_day INTEGER NOT NULL, department TEXT NOT NULL, citizen TEXT NOT NULL, text TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open', episode_id TEXT
    );
    CREATE TABLE sim_votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sim_day INTEGER NOT NULL, question TEXT NOT NULL, method TEXT NOT NULL,
        options_json TEXT NOT NULL, results_json TEXT, status TEXT NOT NULL DEFAULT 'open'
    );
    """,
    # --- Version 4: persistent, versioned city state (Bobbington_City_vNNN) ---------------------------
    """
    CREATE TABLE city_versions (
        number INTEGER PRIMARY KEY,           -- 1 -> Bobbington_City_v001
        parent INTEGER REFERENCES city_versions(number),
        status TEXT NOT NULL,                 -- draft | approved | rejected
        episode_id TEXT,
        video_id TEXT,
        state_hash TEXT NOT NULL,
        changes_json TEXT NOT NULL,
        continuity_json TEXT,
        folder TEXT NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL,
        approved_at TEXT
    );
    CREATE TRIGGER city_versions_immutable BEFORE UPDATE ON city_versions
    WHEN OLD.status IN ('approved', 'rejected')
    BEGIN SELECT RAISE(ABORT, 'approved or rejected city versions are immutable'); END;
    CREATE TRIGGER city_versions_no_delete BEFORE DELETE ON city_versions
    BEGIN SELECT RAISE(ABORT, 'city versions are never deleted'); END;
    """,
    # --- Version 5: user-controlled publishing (caption, hashtags, visibility) and confirmed platform states ---
    """
    ALTER TABLE videos ADD COLUMN caption TEXT;              -- confirmed by the user before any upload
    ALTER TABLE videos ADD COLUMN hashtags TEXT;
    ALTER TABLE videos ADD COLUMN privacy_level TEXT;
    ALTER TABLE videos ADD COLUMN caption_confirmed_at TEXT;
    ALTER TABLE publications ADD COLUMN platform_status TEXT;  -- last status reported by TikTok
    ALTER TABLE publications ADD COLUMN confirmed_at TEXT;     -- when TikTok confirmed the upload
    ALTER TABLE publications ADD COLUMN public_confirmed_at TEXT;
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
