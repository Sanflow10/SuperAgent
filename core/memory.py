import contextlib
import os
import sqlite3
from datetime import UTC, datetime

from core.paths import MEMORY_DB


class MemoryStore:

    def __init__(self, db_path=None):
        self.db = db_path or MEMORY_DB
        self.max_records = int(os.getenv("MAX_MEMORY_RECORDS", "500"))
        self._init_db()

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_run_id
                ON memories(run_id)
                """
            )

    def add(self, run_id: str, kind: str, content: str):
        timestamp = datetime.now(UTC).isoformat()

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memories (run_id, kind, content, created_at) VALUES (?, ?, ?, ?)",
                (run_id, kind, content, timestamp),
            )
            conn.execute(
                """
                DELETE FROM memories
                WHERE id NOT IN (
                    SELECT id FROM memories ORDER BY id DESC LIMIT ?
                )
                """,
                (self.max_records,),
            )

    def recent(self, limit: int = 20, run_id: str | None = None):
        with self._connect() as conn:
            if run_id:
                rows = conn.execute(
                    """
                    SELECT run_id, kind, content, created_at
                    FROM memories WHERE run_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (run_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT run_id, kind, content, created_at
                    FROM memories ORDER BY id DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        return [
            {"run_id": r[0], "kind": r[1], "content": r[2], "created_at": r[3]}
            for r in rows
        ]
