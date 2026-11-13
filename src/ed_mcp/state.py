"""Persistent cursors, alert history, and scoring rules."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ed_mcp.importance import AlertRules
from ed_mcp.timeutil import to_iso

_ALERT_FIELDS = (
    "course_id",
    "course_code",
    "thread_id",
    "number",
    "title",
    "type",
    "category",
    "author",
    "author_role",
    "url",
    "snippet",
    "score",
    "reasons",
    "important",
    "thread_created_at",
    "detected_at",
)


class StateStore:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS cursors (
                course_id INTEGER PRIMARY KEY, max_thread_id INTEGER NOT NULL,
                last_checked_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, course_id INTEGER, course_code TEXT,
                thread_id INTEGER, number INTEGER, title TEXT, type TEXT, category TEXT,
                author TEXT, author_role TEXT, url TEXT, snippet TEXT, score INTEGER,
                reasons TEXT, important INTEGER, thread_created_at TEXT, detected_at TEXT,
                UNIQUE(course_id, thread_id)
            );
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
        """)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def get_cursor(self, course_id: int) -> int | None:
        row = self._conn.execute(
            "SELECT max_thread_id FROM cursors WHERE course_id = ?", (course_id,)
        ).fetchone()
        return row[0] if row else None

    def set_cursor(self, course_id: int, max_thread_id: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO cursors VALUES (?, ?, ?)",
            (course_id, max_thread_id, to_iso(datetime.now(UTC))),
        )
        self._conn.commit()

    def reset_cursor(self, course_id: int | None = None) -> None:
        if course_id is None:
            self._conn.execute("DELETE FROM cursors")
        else:
            self._conn.execute("DELETE FROM cursors WHERE course_id = ?", (course_id,))
        self._conn.commit()

    def record_alert(self, alert: dict) -> bool:
        values = dict(alert)
        values["reasons"] = json.dumps(values["reasons"])
        values["important"] = int(values["important"])
        values["detected_at"] = to_iso(
            datetime.fromisoformat(values["detected_at"]).astimezone(UTC)
        )
        columns = ", ".join(_ALERT_FIELDS)
        placeholders = ", ".join("?" for _ in _ALERT_FIELDS)
        cursor = self._conn.execute(
            f"INSERT OR IGNORE INTO alerts ({columns}) VALUES ({placeholders})",
            tuple(values.get(key) for key in _ALERT_FIELDS),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def recent_alerts(
        self, *, since: datetime | None = None, important_only: bool = True, limit: int = 50
    ) -> list[dict]:
        clauses, params = [], []
        if important_only:
            clauses.append("important = 1")
        if since is not None:
            clauses.append("detected_at >= ?")
            params.append(to_iso(since.astimezone(UTC)))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT {', '.join(_ALERT_FIELDS)} FROM alerts{where} "
            "ORDER BY detected_at DESC, id DESC LIMIT ?",
            params,
        )
        result = []
        for row in rows:
            alert = dict(row)
            alert["reasons"] = json.loads(alert["reasons"])
            alert["important"] = bool(alert["important"])
            result.append(alert)
        return result

    def get_rules(self) -> AlertRules:
        row = self._conn.execute("SELECT value FROM kv WHERE key = 'alert_rules'").fetchone()
        return AlertRules.from_dict(json.loads(row[0])) if row else AlertRules()

    def save_rules(self, rules: AlertRules) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO kv (key, value) VALUES ('alert_rules', ?)",
            (json.dumps(rules.to_dict()),),
        )
        self._conn.commit()
