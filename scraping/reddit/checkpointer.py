from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from typing import Optional, Dict, Any

DEFAULT_CHECKPOINTS_DB = os.getenv("REDDIT_CHECKPOINTS_DB", "storage/reddit/checkpoints.db")


class Checkpointer:
    """
    SQLite-backed checkpoint store.

    Schema:
      checkpoints(job_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at REAL NOT NULL)
    """

    def __init__(self, db_path: str = DEFAULT_CHECKPOINTS_DB):
        self.db_path = db_path
        self._conn = self._connect()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                job_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    async def save_progress(self, job_id: str, checkpoint: Dict[str, Any]) -> None:
        """
        Upsert the checkpoint payload for a job_id.
        """
        payload = json.dumps(checkpoint)
        ts = time.time()

        def _upsert():
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO checkpoints(job_id, payload, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                  payload=excluded.payload,
                  updated_at=excluded.updated_at
                """,
                (job_id, payload, ts),
            )
            self._conn.commit()

        await asyncio.to_thread(_upsert)

    async def load_progress(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Load the checkpoint payload for a job_id, if present.
        """
        def _load():
            cur = self._conn.cursor()
            cur.execute("SELECT payload FROM checkpoints WHERE job_id=?", (job_id,))
            row = cur.fetchone()
            return row[0] if row else None

        raw = await asyncio.to_thread(_load)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None
