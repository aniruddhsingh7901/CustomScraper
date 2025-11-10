from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import asyncpraw
from pydantic import BaseModel, Field


DEFAULT_ACCOUNTS_DB = os.getenv("REDDIT_ACCOUNTS_DB", "storage/reddit/accounts.db")
DEFAULT_PROXIES_JSON = os.getenv("REDDIT_PROXIES_JSON", "storage/reddit/proxies.json")


class AccountCredential(BaseModel):
    client_id: str
    client_secret: str
    username: str
    password: str


class ProxyConfig(BaseModel):
    http: Optional[str] = None
    https: Optional[str] = None
    # Optional metadata fields
    tag: Optional[str] = None
    provider: Optional[str] = None


@dataclass
class AccountLease:
    account: AccountCredential
    proxy: Optional[ProxyConfig]
    reddit: asyncpraw.Reddit
    account_id: str
    proxy_id: Optional[str]
    acquired_at: float
    pool: "AccountPool"

    async def release(self, success: bool = True) -> None:
        try:
            await self.pool.release(self, success=success)
        finally:
            try:
                await self.reddit.close()
            except Exception:
                pass


class RedditClientManager:
    @staticmethod
    def build_client(account: AccountCredential, proxy: Optional[ProxyConfig]) -> asyncpraw.Reddit:
        requestor_kwargs: Dict[str, Any] = {}
        if proxy and (proxy.http or proxy.https):
            proxies: Dict[str, str] = {}
            if proxy.http:
                proxies["http"] = proxy.http
            if proxy.https:
                proxies["https"] = proxy.https
            requestor_kwargs["proxies"] = proxies

        reddit = asyncpraw.Reddit(
            client_id=account.client_id,
            client_secret=account.client_secret,
            username=account.username,
            password=account.password,
            user_agent=f"python: {account.username}",
            requestor_kwargs=requestor_kwargs if requestor_kwargs else None,
        )
        return reddit


class ProxyPool:
    def __init__(self, proxies: Optional[List[ProxyConfig]] = None):
        self._lock = asyncio.Lock()
        self._proxies: List[ProxyConfig] = proxies or []
        self._idx = 0
        # Basic health tracking in-memory
        self._failures: Dict[int, int] = {}

    @classmethod
    async def from_json_file(cls, path: str = DEFAULT_PROXIES_JSON) -> "ProxyPool":
        if not os.path.exists(path):
            return cls([])
        data = await asyncio.to_thread(lambda: json.load(open(path, "r")))
        proxies = [ProxyConfig(**p) for p in data]
        return cls(proxies)

    async def acquire(self) -> Optional[ProxyConfig]:
        async with self._lock:
            if not self._proxies:
                return None
            start = self._idx
            for _ in range(len(self._proxies)):
                idx = self._idx
                self._idx = (self._idx + 1) % len(self._proxies)
                # Simple rotation; could skip if marked unhealthy
                return self._proxies[idx]
            # If empty
            return None

    async def report_failure(self, proxy: ProxyConfig) -> None:
        async with self._lock:
            try:
                idx = self._proxies.index(proxy)
            except ValueError:
                return
            self._failures[idx] = self._failures.get(idx, 0) + 1

    async def report_success(self, proxy: ProxyConfig) -> None:
        async with self._lock:
            try:
                idx = self._proxies.index(proxy)
            except ValueError:
                return
            # decay failures
            cur = self._failures.get(idx, 0)
            if cur > 0:
                self._failures[idx] = cur - 1


class AccountPool:
    """
    SQLite-backed AccountPool.
    Schema:
      accounts(account_id TEXT PRIMARY KEY, client_id TEXT, client_secret TEXT,
               username TEXT, password TEXT, status TEXT, cooldown_until REAL,
               fail_count INTEGER, last_error TEXT, proxy_id TEXT)
      proxies(proxy_id TEXT PRIMARY KEY, http TEXT, https TEXT, tag TEXT, provider TEXT)
    """

    def __init__(
        self,
        db_path: str = DEFAULT_ACCOUNTS_DB,
        proxies_path: Optional[str] = DEFAULT_PROXIES_JSON,
        active_fraction: float = 0.75,
        cooldown_seconds: int = 60,
    ):
        self.db_path = db_path
        self.active_fraction = active_fraction
        self.cooldown_seconds = cooldown_seconds
        self._conn = self._connect()
        self._init_schema()
        self._lock = asyncio.Lock()
        self._proxy_pool: Optional[ProxyPool] = None
        self._proxies_path = proxies_path

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
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                client_secret TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ready',
                cooldown_until REAL DEFAULT 0,
                fail_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                proxy_id TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS proxies (
                proxy_id TEXT PRIMARY KEY,
                http TEXT,
                https TEXT,
                tag TEXT,
                provider TEXT
            )
            """
        )
        self._conn.commit()

    async def _ensure_proxy_pool(self) -> None:
        if self._proxy_pool is None:
            if self._proxies_path and os.path.exists(self._proxies_path):
                self._proxy_pool = await ProxyPool.from_json_file(self._proxies_path)
            else:
                self._proxy_pool = ProxyPool([])

    async def add_account(self, account_id: str, cred: AccountCredential) -> None:
        def _add():
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO accounts(account_id, client_id, client_secret, username, password, status, cooldown_until, fail_count, last_error, proxy_id)
                VALUES(?, ?, ?, ?, ?, COALESCE((SELECT status FROM accounts WHERE account_id=?), 'ready'),
                       COALESCE((SELECT cooldown_until FROM accounts WHERE account_id=?), 0),
                       COALESCE((SELECT fail_count FROM accounts WHERE account_id=?), 0),
                       COALESCE((SELECT last_error FROM accounts WHERE account_id=?), NULL),
                       COALESCE((SELECT proxy_id FROM accounts WHERE account_id=?), NULL)
                )
                """,
                (
                    account_id,
                    cred.client_id,
                    cred.client_secret,
                    cred.username,
                    cred.password,
                    account_id,
                    account_id,
                    account_id,
                    account_id,
                    account_id,
                ),
            )
            self._conn.commit()

        await asyncio.to_thread(_add)

    async def add_proxy(self, proxy_id: str, proxy: ProxyConfig) -> None:
        def _add():
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO proxies(proxy_id, http, https, tag, provider)
                VALUES(?, ?, ?, ?, ?)
                """,
                (proxy_id, proxy.http, proxy.https, proxy.tag, proxy.provider),
            )
            self._conn.commit()

        await asyncio.to_thread(_add)

    async def acquire(self) -> AccountLease:
        """
        Select a ready account (respecting cooldown), assign a proxy, and return a ready asyncpraw client.
        Marks account status as 'leased' until release().
        """
        await self._ensure_proxy_pool()

        async with self._lock:
            now = time.time()

            def _select_and_mark() -> Optional[Dict[str, Any]]:
                cur = self._conn.cursor()
                cur.execute(
                    """
                    SELECT account_id, client_id, client_secret, username, password
                    FROM accounts
                    WHERE status='ready' AND cooldown_until <= ?
                    ORDER BY fail_count ASC
                    LIMIT 1
                    """,
                    (now,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                account_id, client_id, client_secret, username, password = row
                cur.execute(
                    "UPDATE accounts SET status='leased' WHERE account_id=?",
                    (account_id,),
                )
                self._conn.commit()
                return {
                    "account_id": account_id,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "username": username,
                    "password": password,
                }

            row = await asyncio.to_thread(_select_and_mark)
            if not row:
                # No ready accounts; wait a bit and retry
                await asyncio.sleep(1.0)
                # Second attempt
                row = await asyncio.to_thread(_select_and_mark)
                if not row:
                    raise RuntimeError("No ready Reddit accounts available for leasing")

            account = AccountCredential(
                client_id=row["client_id"],
                client_secret=row["client_secret"],
                username=row["username"],
                password=row["password"],
            )

            proxy: Optional[ProxyConfig] = await self._proxy_pool.acquire() if self._proxy_pool else None

            reddit = RedditClientManager.build_client(account, proxy)
            lease = AccountLease(
                account=account,
                proxy=proxy,
                reddit=reddit,
                account_id=row["account_id"],
                proxy_id=None,
                acquired_at=time.time(),
                pool=self,
            )
            return lease

    async def release(self, lease: AccountLease, success: bool = True) -> None:
        now = time.time()

        def _update():
            cur = self._conn.cursor()
            if success:
                cur.execute(
                    "UPDATE accounts SET status='ready', cooldown_until=?, fail_count=MAX(fail_count-1, 0) WHERE account_id=?",
                    (now + max(0, self.cooldown_seconds // 4), lease.account_id),
                )
            else:
                cur.execute(
                    "UPDATE accounts SET status='ready', cooldown_until=?, fail_count=fail_count+1 WHERE account_id=?",
                    (now + self.cooldown_seconds, lease.account_id),
                )
            self._conn.commit()

        await asyncio.to_thread(_update)

    async def cooldown(self, lease: AccountLease, seconds: int, reason: Optional[str] = None) -> None:
        until = time.time() + seconds

        def _cd():
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE accounts SET status='ready', cooldown_until=?, last_error=? WHERE account_id=?",
                (until, reason, lease.account_id),
            )
            self._conn.commit()

        await asyncio.to_thread(_cd)

    async def quarantine(self, lease: AccountLease, reason: str) -> None:
        def _q():
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE accounts SET status='quarantine', last_error=? WHERE account_id=?",
                (reason, lease.account_id),
            )
            self._conn.commit()

        await asyncio.to_thread(_q)

    async def health_report(self) -> Dict[str, Any]:
        def _report():
            cur = self._conn.cursor()
            cur.execute(
                "SELECT status, COUNT(*) FROM accounts GROUP BY status"
            )
            rows = cur.fetchall()
            return {status: count for status, count in rows}

        return await asyncio.to_thread(_report)
