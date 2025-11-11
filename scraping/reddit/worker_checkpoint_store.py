from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any


DEFAULT_ACCOUNTS_DB = os.getenv("REDDIT_ACCOUNTS_DB", "storage/reddit/accounts.db")


@dataclass
class WorkerCheckpoint:
    worker_id: str
    account_id: Optional[str]
    last_subreddit: Optional[str]
    last_post_id: Optional[str]
    last_comment_id: Optional[str]
    updated_at: float


class WorkerCheckpointStore:
    """
    SQLite-backed store for worker checkpoints inside accounts.db

    Schema (created by AccountPool._init_schema already):
      checkpoints(
        worker_id TEXT PRIMARY KEY,
        account_id TEXT,
        last_subreddit TEXT,
        last_post_id TEXT,
        last_comment_id TEXT,
        updated_at REAL
      )
    """

    def __init__(self, db_path: str = DEFAULT_ACCOUNTS_DB):
        self.db_path = db_path
        self._conn = self._connect()

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    async def upsert(
        self,
        worker_id: str,
        account_id: Optional[str],
        last_subreddit: Optional[str],
        last_post_id: Optional[str],
        last_comment_id: Optional[str],
        updated_at: Optional[float] = None,
    ) -> None:
        ts = updated_at if updated_at is not None else time.time()

        def _op():
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO checkpoints(worker_id, account_id, last_subreddit, last_post_id, last_comment_id, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    account_id=excluded.account_id,
                    last_subreddit=excluded.last_subreddit,
                    last_post_id=excluded.last_post_id,
                    last_comment_id=excluded.last_comment_id,
                    updated_at=excluded.updated_at
                """,
                (worker_id, account_id, last_subreddit, last_post_id, last_comment_id, ts),
            )
            self._conn.commit()

        await asyncio.to_thread(_op)

    async def get(self, worker_id: str) -> Optional[WorkerCheckpoint]:
        def _op() -> Optional[WorkerCheckpoint]:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT worker_id, account_id, last_subreddit, last_post_id, last_comment_id, updated_at
                FROM checkpoints WHERE worker_id=?
                """,
                (worker_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return WorkerCheckpoint(
                worker_id=row[0],
                account_id=row[1],
                last_subreddit=row[2],
                last_post_id=row[3],
                last_comment_id=row[4],
                updated_at=float(row[5]) if row[5] is not None else 0.0,
            )

        return await asyncio.to_thread(_op)

    async def list_all(self) -> list[WorkerCheckpoint]:
        def _op() -> list[WorkerCheckpoint]:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT worker_id, account_id, last_subreddit, last_post_id, last_comment_id, updated_at
                FROM checkpoints ORDER BY updated_at DESC
                """
            )
            rows = cur.fetchall()
            out: list[WorkerCheckpoint] = []
            for r in rows:
                out.append(
                    WorkerCheckpoint(
                        worker_id=r[0],
                        account_id=r[1],
                        last_subreddit=r[2],
                        last_post_id=r[3],
                        last_comment_id=r[4],
                        updated_at=float(r[5]) if r[5] is not None else 0.0,
                    )
                )
            return out

        return await asyncio.to_thread(_op)
