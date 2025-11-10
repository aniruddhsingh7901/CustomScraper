from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from typing import Optional

DEFAULT_RATE_DB = os.getenv("REDDIT_RATE_DB", "storage/reddit/ratelimiter.db")


class SqliteTokenBucketLimiter:
    """
    Simple SQLite-backed token bucket rate limiter.

    Schema:
      buckets(bucket TEXT PRIMARY KEY, capacity REAL, tokens REAL, refill_rate REAL, updated_at REAL)

    - capacity: max tokens
    - tokens: current tokens available
    - refill_rate: tokens per second
    - updated_at: last refill timestamp (epoch seconds float)
    """

    def __init__(self, db_path: str = DEFAULT_RATE_DB):
        self.db_path = db_path
        self._conn = self._connect()
        self._init_schema()
        self._lock = asyncio.Lock()

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
            CREATE TABLE IF NOT EXISTS buckets (
                bucket TEXT PRIMARY KEY,
                capacity REAL NOT NULL,
                tokens REAL NOT NULL,
                refill_rate REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    async def ensure_bucket(self, name: str, capacity: float, refill_rate: float) -> None:
        """
        Ensure the bucket row exists; if not, create with full tokens.
        """
        now = time.time()

        def _ensure():
            cur = self._conn.cursor()
            cur.execute("SELECT bucket FROM buckets WHERE bucket=?", (name,))
            row = cur.fetchone()
            if not row:
                cur.execute(
                    "INSERT INTO buckets(bucket, capacity, tokens, refill_rate, updated_at) VALUES(?, ?, ?, ?, ?)",
                    (name, capacity, capacity, refill_rate, now),
                )
                self._conn.commit()

        await asyncio.to_thread(_ensure)

    async def acquire(self, name: str, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """
        Attempt to acquire tokens. If not enough tokens, wait until available or timeout.
        Returns True if acquired, False if timeout elapsed.
        """
        deadline = None if timeout is None else time.time() + timeout
        while True:
            acquired = await self._try_acquire_once(name, tokens)
            if acquired:
                return True
            # Not enough tokens; compute next availability based on refill rate
            if deadline is not None and time.time() >= deadline:
                return False
            await asyncio.sleep(0.1)

    async def _try_acquire_once(self, name: str, tokens: float) -> bool:
        async with self._lock:
            now = time.time()

            def _op() -> bool:
                cur = self._conn.cursor()
                cur.execute(
                    "SELECT capacity, tokens, refill_rate, updated_at FROM buckets WHERE bucket=?",
                    (name,),
                )
                row = cur.fetchone()
                if not row:
                    # default bucket if not ensured: small capacity/refill to be safe
                    capacity, current, refill, updated_at = 5.0, 5.0, 5.0, now
                    cur.execute(
                        "INSERT OR REPLACE INTO buckets(bucket, capacity, tokens, refill_rate, updated_at) VALUES(?, ?, ?, ?, ?)",
                        (name, capacity, current, refill, now),
                    )
                else:
                    capacity, current, refill, updated_at = row
                # refill
                elapsed = max(0.0, now - float(updated_at))
                current = min(float(capacity), float(current) + float(refill) * elapsed)
                if current >= tokens:
                    current -= tokens
                    cur.execute(
                        "UPDATE buckets SET tokens=?, updated_at=? WHERE bucket=?",
                        (current, now, name),
                    )
                    self._conn.commit()
                    return True
                else:
                    # just update updated_at and tokens (refilled)
                    cur.execute(
                        "UPDATE buckets SET tokens=?, updated_at=? WHERE bucket=?",
                        (current, now, name),
                    )
                    self._conn.commit()
                    return False

            return await asyncio.to_thread(_op)
