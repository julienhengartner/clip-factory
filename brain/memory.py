"""Dauerhaftes Gedächtnis des Brain Agent (High-Level-API über storage.database)."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any

from storage.database import Database, dumps, loads, today_prefix, utcnow
from storage.models import Idea, ResearchItem, VideoStatus


class Memory:
    def __init__(self, db: Database):
        self.db = db

    # --- Ereignisse / Fehlerprotokoll ------------------------------------------
    def log(self, level: str, source: str, message: str, video_id: str | None = None, run_id: int | None = None) -> None:
        self.db.execute("INSERT INTO events (video_id, run_id, level, source, message, created_at) VALUES (?,?,?,?,?,?)",
                        (video_id, run_id, level, source, message[:4000], utcnow()))

    def events(self, video_id: str | None = None, level: str | None = None, limit: int = 200) -> list[dict]:
        sql, params = "SELECT * FROM events WHERE 1=1", []
        if video_id:
            sql += " AND video_id = ?"
            params.append(video_id)
        if level:
            sql += " AND level = ?"
            params.append(level)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return list(reversed(self.db.query(sql, params)))

    # --- Recherche ----------------------------------------------------------------
    def add_research(self, item: ResearchItem) -> int:
        existing = self.db.query_one("SELECT id FROM research_items WHERE url = ?", (item.url,))
        if existing:
            self.db.execute("UPDATE research_items SET summary=?, verified=?, verification_note=?, category=? WHERE id=?",
                            (item.summary, int(item.verified), item.verification_note, item.category, existing["id"]))
            return existing["id"]
        return self.db.execute(
            "INSERT INTO research_items (title, summary, url, source, category, published_at, verified, verification_note,"
            " fetched_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (item.title, item.summary, item.url, item.source, item.category, item.published_at, int(item.verified),
             item.verification_note, utcnow()))

    def get_research(self, ids: list[int]) -> list[ResearchItem]:
        if not ids:
            return []
        rows = self.db.query(f"SELECT * FROM research_items WHERE id IN ({','.join('?' * len(ids))})", ids)
        by_id = {r["id"]: r for r in rows}
        return [self._research(by_id[i]) for i in ids if i in by_id]

    def recent_research(self, limit: int = 50, verified_only: bool = False) -> list[ResearchItem]:
        sql = "SELECT * FROM research_items" + (" WHERE verified = 1" if verified_only else "") + " ORDER BY id DESC LIMIT ?"
        return [self._research(r) for r in self.db.query(sql, (limit,))]

    @staticmethod
    def _research(row: dict) -> ResearchItem:
        return ResearchItem(**{**{k: row[k] for k in ResearchItem.model_fields if k in row}, "verified": bool(row["verified"])})

    # --- Ideen ----------------------------------------------------------------------
    def add_idea(self, idea: Idea) -> int:
        ts = utcnow()
        return self.db.execute(
            "INSERT INTO ideas (title, angle, category, research_ids, score, origin, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (idea.title, idea.angle, idea.category, dumps(idea.research_ids), idea.score, idea.origin, idea.status, ts, ts))

    def get_idea(self, idea_id: int) -> Idea | None:
        row = self.db.query_one("SELECT * FROM ideas WHERE id = ?", (idea_id,))
        return self._idea(row) if row else None

    def list_ideas(self, status: str | None = "new", limit: int = 100) -> list[Idea]:
        if status:
            rows = self.db.query("SELECT * FROM ideas WHERE status = ? ORDER BY score DESC, id DESC LIMIT ?", (status, limit))
        else:
            rows = self.db.query("SELECT * FROM ideas ORDER BY id DESC LIMIT ?", (limit,))
        return [self._idea(r) for r in rows]

    def update_idea(self, idea_id: int, **fields: Any) -> None:
        allowed = {"status", "score", "angle"}
        if set(fields) - allowed:
            raise ValueError(f"Unbekannte Felder: {set(fields) - allowed}")
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE ideas SET {cols}, updated_at = ? WHERE id = ?", (*fields.values(), utcnow(), idea_id))

    def idea_titles(self) -> list[str]:
        return [r["title"] for r in self.db.query("SELECT title FROM ideas")]

    @staticmethod
    def _idea(row: dict) -> Idea:
        return Idea(id=row["id"], title=row["title"], angle=row["angle"], category=row["category"],
                    research_ids=loads(row["research_ids"], []), score=row["score"], origin=row["origin"],
                    status=row["status"])

    # --- Videos ---------------------------------------------------------------------
    _VIDEO_FIELDS = {"status", "title", "hook", "hook_pattern", "script_json", "scenes_json", "qc_json", "video_path",
                     "thumbnail_path", "duration_s", "words", "wpm", "voice_provider", "image_provider",
                     "script_provider", "revisions", "render_attempts", "error", "approved_at", "published_at",
                     "category", "topic"}

    def create_video(self, topic: str, idea_id: int | None = None, category: str = "allgemein") -> dict:
        vid = uuid.uuid4().hex[:12]
        ts = utcnow()
        self.db.execute("INSERT INTO videos (id, idea_id, topic, category, status, created_at, updated_at)"
                        " VALUES (?,?,?,?,?,?,?)", (vid, idea_id, topic, category, VideoStatus.PRODUCING.value, ts, ts))
        return self.get_video(vid)  # type: ignore[return-value]

    def update_video(self, video_id: str, **fields: Any) -> dict:
        unknown = set(fields) - self._VIDEO_FIELDS
        if unknown:
            raise ValueError(f"Unbekannte Video-Felder: {unknown}")
        for k in ("script_json", "scenes_json", "qc_json"):
            if k in fields and not isinstance(fields[k], (str, type(None))):
                fields[k] = dumps(fields[k])
        if "status" in fields and isinstance(fields["status"], VideoStatus):
            fields["status"] = fields["status"].value
        if fields:
            cols = ", ".join(f"{k} = ?" for k in fields)
            n = self.db.execute(f"UPDATE videos SET {cols}, updated_at = ? WHERE id = ?", (*fields.values(), utcnow(), video_id))
            if n == 0:
                raise KeyError(video_id)
        return self.get_video(video_id)  # type: ignore[return-value]

    def get_video(self, video_id: str) -> dict | None:
        row = self.db.query_one("SELECT * FROM videos WHERE id = ?", (video_id,))
        return self._video(row) if row else None

    def list_videos(self, status: str | list[str] | None = None, limit: int = 100) -> list[dict]:
        if status:
            statuses = [status] if isinstance(status, str) else status
            rows = self.db.query(f"SELECT * FROM videos WHERE status IN ({','.join('?' * len(statuses))})"
                                 " ORDER BY created_at DESC, rowid DESC LIMIT ?", (*statuses, limit))
        else:
            rows = self.db.query("SELECT * FROM videos ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))
        return [self._video(r) for r in rows]

    def videos_created_today(self) -> int:
        return self.db.scalar("SELECT COUNT(*) FROM videos WHERE created_at LIKE ?", (today_prefix() + "%",)) or 0

    def produced_topics(self, limit: int = 200) -> list[str]:
        rows = self.db.query("SELECT topic, title FROM videos WHERE status NOT IN ('failed') ORDER BY rowid DESC LIMIT ?",
                             (limit,))
        return [f"{r['topic']} {r['title'] or ''}".strip() for r in rows]

    @staticmethod
    def _video(row: dict) -> dict:
        d = dict(row)
        d["script"] = loads(d.pop("script_json"))
        d["scenes"] = loads(d.pop("scenes_json"))
        d["qc"] = loads(d.pop("qc_json"))
        return d

    # --- Hooks -----------------------------------------------------------------------
    def add_hook(self, video_id: str, text: str, pattern: str, score: float, chosen: bool) -> None:
        self.db.execute("INSERT INTO hooks (video_id, text, pattern, score, chosen, created_at) VALUES (?,?,?,?,?,?)",
                        (video_id, text, pattern, score, int(chosen), utcnow()))

    # --- Veröffentlichungen ----------------------------------------------------------
    def add_publication(self, video_id: str, platform: str, mode: str, status: str, publish_id: str | None,
                        caption: str, privacy_level: str | None, message: str = "") -> int:
        ts = utcnow()
        return self.db.execute(
            "INSERT INTO publications (video_id, platform, mode, publish_id, status, caption, privacy_level, message,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (video_id, platform, mode, publish_id, status, caption, privacy_level, message, ts, ts))

    def update_publication(self, pub_id: int, **fields: Any) -> None:
        allowed = {"status", "message", "external_id", "publish_id"}
        if set(fields) - allowed:
            raise ValueError(f"Unbekannte Felder: {set(fields) - allowed}")
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE publications SET {cols}, updated_at = ? WHERE id = ?", (*fields.values(), utcnow(), pub_id))

    def publications(self, video_id: str | None = None, status: list[str] | None = None) -> list[dict]:
        sql, params = "SELECT * FROM publications WHERE 1=1", []
        if video_id:
            sql += " AND video_id = ?"
            params.append(video_id)
        if status:
            sql += f" AND status IN ({','.join('?' * len(status))})"
            params.extend(status)
        return self.db.query(sql + " ORDER BY id", params)

    # --- Performance -----------------------------------------------------------------
    def add_performance(self, platform: str, external_id: str, video_id: str | None = None, **metrics: int | None) -> None:
        cols = ["views", "likes", "comments", "shares", "saves", "reach"]
        vals = [metrics.get(c) for c in cols]
        self.db.execute(f"INSERT INTO performance (video_id, platform, external_id, {', '.join(cols)}, collected_at)"
                        f" VALUES (?,?,?,{','.join('?' * len(cols))},?)", (video_id, platform, external_id, *vals, utcnow()))

    def latest_performance(self, platform: str | None = None) -> list[dict]:
        sql = ("SELECT p.* FROM performance p JOIN (SELECT platform, external_id, MAX(id) AS mid FROM performance"
               " GROUP BY platform, external_id) l ON p.id = l.mid")
        params: list = []
        if platform:
            sql += " WHERE p.platform = ?"
            params.append(platform)
        return self.db.query(sql, params)

    # --- Kommentare ------------------------------------------------------------------
    def upsert_comment(self, platform: str, external_id: str, text: str, media_id: str | None, author: str | None,
                       like_count: int | None, commented_at: str | None) -> bool:
        """Speichert einen Kommentar; Autorennamen werden nur als Hash abgelegt. True = neu."""
        author_hash = hashlib.sha256(author.encode()).hexdigest()[:16] if author else None
        exists = self.db.query_one("SELECT id FROM comments WHERE platform=? AND external_id=?", (platform, external_id))
        if exists:
            self.db.execute("UPDATE comments SET like_count=? WHERE id=?", (like_count, exists["id"]))
            return False
        self.db.execute("INSERT INTO comments (platform, external_id, media_id, text, author_hash, like_count,"
                        " commented_at, created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (platform, external_id, media_id, text, author_hash, like_count, commented_at, utcnow()))
        return True

    def unanalyzed_comments(self, limit: int = 500) -> list[dict]:
        return self.db.query("SELECT * FROM comments WHERE analyzed_at IS NULL ORDER BY id LIMIT ?", (limit,))

    def set_comment_analysis(self, comment_id: int, category: str, sentiment: float, keywords: list[str]) -> None:
        self.db.execute("UPDATE comments SET category=?, sentiment=?, keywords=?, analyzed_at=? WHERE id=?",
                        (category, sentiment, dumps(keywords), utcnow(), comment_id))

    def comments(self, category: str | None = None, limit: int = 500) -> list[dict]:
        if category:
            return self.db.query("SELECT * FROM comments WHERE category=? ORDER BY id DESC LIMIT ?", (category, limit))
        return self.db.query("SELECT * FROM comments ORDER BY id DESC LIMIT ?", (limit,))

    # --- Follower --------------------------------------------------------------------
    def add_follower_stats(self, platform: str, followers: int | None, follows: int | None, media_count: int | None) -> None:
        self.db.execute("INSERT INTO follower_stats (platform, followers, follows, media_count, collected_at) VALUES (?,?,?,?,?)",
                        (platform, followers, follows, media_count, utcnow()))

    def follower_history(self, platform: str, limit: int = 60) -> list[dict]:
        return list(reversed(self.db.query("SELECT * FROM follower_stats WHERE platform=? ORDER BY id DESC LIMIT ?",
                                           (platform, limit))))

    # --- Erkenntnisse (Lernen, Stil, Strategie) -----------------------------------
    def set_insight(self, kind: str, key: str, value: Any, confidence: float = 0.0) -> None:
        ts = utcnow()
        self.db.execute(
            "INSERT INTO insights (kind, key, value_json, confidence, created_at, updated_at) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(kind, key) DO UPDATE SET value_json=excluded.value_json, confidence=excluded.confidence,"
            " updated_at=excluded.updated_at", (kind, key, dumps(value), confidence, ts, ts))

    def get_insight(self, kind: str, key: str, default: Any = None) -> Any:
        row = self.db.query_one("SELECT value_json FROM insights WHERE kind=? AND key=?", (kind, key))
        return loads(row["value_json"]) if row else default

    def insights(self, kind: str) -> dict[str, Any]:
        return {r["key"]: loads(r["value_json"]) for r in self.db.query("SELECT key, value_json FROM insights WHERE kind=?",
                                                                       (kind,))}

    # --- Einstellungen (z. B. Automatik an/aus) -----------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.db.query_one("SELECT value_json FROM settings_kv WHERE key=?", (key,))
        return loads(row["value_json"]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        self.db.execute("INSERT INTO settings_kv (key, value_json, updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE"
                        " SET value_json=excluded.value_json, updated_at=excluded.updated_at", (key, dumps(value), utcnow()))

    # --- API-Nutzung ----------------------------------------------------------------
    def record_api_call(self, provider: str, operation: str, units: float = 1) -> None:
        self.db.execute("INSERT INTO api_usage (provider, operation, units, created_at) VALUES (?,?,?,?)",
                        (provider, operation, units, utcnow()))

    def paid_calls_today(self) -> int:
        return self.db.scalar("SELECT COUNT(*) FROM api_usage WHERE created_at LIKE ?", (today_prefix() + "%",)) or 0

    # --- Läufe ----------------------------------------------------------------------
    def start_run(self, kind: str) -> int:
        return self.db.execute("INSERT INTO runs (kind, status, started_at) VALUES (?,?,?)", (kind, "running", utcnow()))

    def finish_run(self, run_id: int, status: str, summary: dict) -> None:
        self.db.execute("UPDATE runs SET status=?, summary_json=?, finished_at=? WHERE id=?",
                        (status, dumps(summary), utcnow(), run_id))

    def runs(self, limit: int = 20) -> list[dict]:
        return self.db.query("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))

    # --- OAuth-State (CSRF-Schutz) --------------------------------------------------
    def add_oauth_state(self, state: str, provider: str) -> None:
        self.db.execute("INSERT INTO oauth_states (state, provider, created_at) VALUES (?,?,?)", (state, provider, utcnow()))

    def consume_oauth_state(self, state: str, provider: str) -> bool:
        return self.db.execute("DELETE FROM oauth_states WHERE state=? AND provider=?", (state, provider)) > 0
