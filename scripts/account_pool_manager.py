#!/usr/bin/env python3
"""
Account Pool Manager (24/7 via PM2)

Responsibilities:
- Continuously maintain the Reddit account pool state in SQLite:
  * Probe ready accounts (not cooling, not quarantined) with a lightweight API call
  * Detect auth/rate-limit/network issues -> set cooldown or quarantine
  * Decay fail_count on healthy checks
- Maintain global rate-limiter buckets in SQLite (ensure exists/tunable via env)
- Publish simple Prometheus metrics (counts by status) on an HTTP port
- Do NOT "lease" accounts; this is a non-intrusive health manager that does not flip to 'leased'

Configuration (env):
- REDDIT_ACCOUNTS_DB: path to storage/reddit/accounts.db (default)
- REDDIT_PROXIES_JSON: path to storage/reddit/proxies.json (default)
- ACCOUNT_MANAGER_INTERVAL: seconds between maintenance cycles (default 60)
- ACCOUNT_MANAGER_COOLDOWN_BAD: cooldown seconds for transient failures (default 60)
- ACCOUNT_MANAGER_COOLDOWN_RATE: cooldown seconds for rate-limit (default 120)
- ACCOUNT_MANAGER_QUARANTINE_FAILS: fail_count threshold to quarantine (default 5)
- RATE_BUCKET_NAME: (default "replace_more")
- RATE_BUCKET_CAPACITY: (default 5.0)
- RATE_BUCKET_REFILL: (default 2.0 tokens/sec)
- PROM_PORT: Prometheus HTTP port (default 9108)
"""

import asyncio
import json
import os
import sqlite3
import sys
import time
import signal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure repo root sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncpraw
from dotenv import load_dotenv
from prometheus_client import start_http_server, Gauge, Counter

from scraping.reddit.session_pool import AccountCredential, ProxyConfig, RedditClientManager
from scraping.reddit.rate_limiter import SqliteTokenBucketLimiter


# Env/config -------------------------------------------------------------------

ACCOUNTS_DB = os.environ.get("REDDIT_ACCOUNTS_DB", "storage/reddit/accounts.db")
PROXIES_JSON = os.environ.get("REDDIT_PROXIES_JSON", "storage/reddit/proxies.json")

INTERVAL = int(os.environ.get("ACCOUNT_MANAGER_INTERVAL", "60"))
COOLDOWN_BAD = int(os.environ.get("ACCOUNT_MANAGER_COOLDOWN_BAD", "60"))
COOLDOWN_RATE = int(os.environ.get("ACCOUNT_MANAGER_COOLDOWN_RATE", "120"))
QUARANTINE_FAILS = int(os.environ.get("ACCOUNT_MANAGER_QUARANTINE_FAILS", "5"))

RATE_BUCKET_NAME = os.environ.get("RATE_BUCKET_NAME", "replace_more")
RATE_BUCKET_CAPACITY = float(os.environ.get("RATE_BUCKET_CAPACITY", "5.0"))
RATE_BUCKET_REFILL = float(os.environ.get("RATE_BUCKET_REFILL", "2.0"))

PROM_PORT = int(os.environ.get("PROM_PORT", "9108"))

# Prometheus metrics ------------------------------------------------------------

g_accounts_ready = Gauge("reddit_pool_ready_accounts", "Accounts with status=ready and not cooling")
g_accounts_leased = Gauge("reddit_pool_leased_accounts", "Accounts with status=leased")
g_accounts_quarantine = Gauge("reddit_pool_quarantine_accounts", "Accounts with status=quarantine")
g_accounts_cooling = Gauge("reddit_pool_cooling_accounts", "Accounts in cooldown (ready but cooldown_until > now)")
c_account_check_total = Counter("reddit_pool_account_check_total", "Total account health checks performed")
c_account_quarantine_total = Counter("reddit_pool_account_quarantine_total", "Total times an account was quarantined")
c_account_cooldown_total = Counter("reddit_pool_account_cooldown_total", "Total times an account was cooldowned")

# Globals ----------------------------------------------------------------------

_shutdown = False
_proxy_list: List[ProxyConfig] = []
_proxy_idx = 0


def _handle_signal(signum, frame):
    global _shutdown
    _shutdown = True
    print(f"[account_pool_manager] Received signal {signum}. Shutting down gracefully...")


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# SQLite helpers ----------------------------------------------------------------

def _connect_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(ACCOUNTS_DB), exist_ok=True)
    conn = sqlite3.connect(ACCOUNTS_DB, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _fetch_accounts(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    now = time.time()
    cur = conn.cursor()
    # Fetch all 'ready' accounts; we will classify which are cooling locally
    cur.execute(
        """
        SELECT account_id, client_id, client_secret, username, password, status, cooldown_until, fail_count, last_error
        FROM accounts
        WHERE status IN ('ready','leased','quarantine')
        """
    )
    rows = cur.fetchall()
    cols = ["account_id","client_id","client_secret","username","password","status","cooldown_until","fail_count","last_error"]
    return [dict(zip(cols, r)) for r in rows]


def _update_on_success(conn: sqlite3.Connection, account_id: str):
    # success => keep status 'ready', short cooldown decay, fail_count decay
    now = time.time()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE accounts
        SET status='ready',
            cooldown_until=MAX(0, MIN(cooldown_until, ?)),
            fail_count=CASE WHEN fail_count > 0 THEN fail_count - 1 ELSE 0 END,
            last_error=NULL
        WHERE account_id=?
        """,
        (now, account_id),
    )
    conn.commit()


def _cooldown(conn: sqlite3.Connection, account_id: str, seconds: int, reason: str):
    until = time.time() + max(1, seconds)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE accounts
        SET status='ready',
            cooldown_until=?,
            fail_count=fail_count+1,
            last_error=?
        WHERE account_id=?
        """,
        (until, reason, account_id),
    )
    conn.commit()
    c_account_cooldown_total.inc()


def _quarantine(conn: sqlite3.Connection, account_id: str, reason: str):
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE accounts
        SET status='quarantine',
            last_error=?
        WHERE account_id=?
        """,
        (reason, account_id),
    )
    conn.commit()
    c_account_quarantine_total.inc()


def _classify_counts(rows: List[Dict[str, Any]]) -> Tuple[int,int,int,int]:
    now = time.time()
    ready = 0
    leased = 0
    quarantine = 0
    cooling = 0
    for r in rows:
        st = r["status"]
        if st == "ready":
            if float(r["cooldown_until"] or 0) > now:
                cooling += 1
            else:
                ready += 1
        elif st == "leased":
            leased += 1
        elif st == "quarantine":
            quarantine += 1
    return ready, leased, quarantine, cooling


# Proxies -----------------------------------------------------------------------

def _load_proxies(path: str) -> List[ProxyConfig]:
    if not os.path.exists(path):
        print(f"[account_pool_manager] WARN: proxies.json not found at {path}; continuing without proxies.")
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        proxies: List[ProxyConfig] = []
        for p in data:
            proxies.append(ProxyConfig(http=p.get("http"), https=p.get("https"), tag=p.get("tag"), provider=p.get("provider")))
        return proxies
    except Exception as e:
        print(f"[account_pool_manager] ERROR reading proxies.json: {e}")
        return []


def _next_proxy() -> Optional[ProxyConfig]:
    global _proxy_idx
    if not _proxy_list:
        return None
    p = _proxy_list[_proxy_idx % len(_proxy_list)]
    _proxy_idx = (_proxy_idx + 1) % len(_proxy_list)
    return p


# Health check ------------------------------------------------------------------

async def _health_probe(account: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Lightweight probe to validate credentials + basic API reachability.
    - Builds a Reddit client with a rotated proxy (if any)
    - Executes a very small call: fetch 1 item from r/all.new
    Returns (ok, reason)
    """
    cred = AccountCredential(
        client_id=account["client_id"],
        client_secret=account["client_secret"],
        username=account["username"],
        password=account["password"],
    )
    proxy = _next_proxy()
    reddit: Optional[asyncpraw.Reddit] = None
    try:
        reddit = RedditClientManager.build_client(cred, proxy)
        # minimal call to trigger auth + request — avoid heavy endpoints
        sub = await reddit.subreddit("all")
        # Use async iterator limited to 1
        agen = sub.new(limit=1)
        async for _ in agen:
            break
        return True, "ok"
    except Exception as e:
        msg = str(e)
        # Simple heuristic for rate-limit vs auth
        if "Too Many Requests" in msg or "RATELIMIT" in msg or "429" in msg:
            return False, "rate-limit"
        if "401" in msg or "403" in msg or "invalid_grant" in msg or "Forbidden" in msg or "Unauthorized" in msg:
            return False, "auth"
        return False, "network"
    finally:
        try:
            if reddit is not None:
                await reddit.close()
        except Exception:
            pass


# Main loop ---------------------------------------------------------------------

async def _maintain_accounts(conn: sqlite3.Connection):
    rows = await asyncio.to_thread(lambda: _fetch_accounts(conn))
    now = time.time()

    # Update metrics (counts by status)
    ready, leased, quarantine, cooling = _classify_counts(rows)
    g_accounts_ready.set(ready)
    g_accounts_leased.set(leased)
    g_accounts_quarantine.set(quarantine)
    g_accounts_cooling.set(cooling)

    # Iterate ready & not cooling accounts only
    to_check = [r for r in rows if r["status"] == "ready" and float(r["cooldown_until"] or 0) <= now]

    # Concurrency limiter
    sem = asyncio.Semaphore(10)
    async def _check_one(r: Dict[str, Any]):
        c_account_check_total.inc()
        async with sem:
            ok, reason = await _health_probe(r)
            if ok:
                await asyncio.to_thread(lambda: _update_on_success(conn, r["account_id"]))
            else:
                # Escalation logic
                fails = int(r.get("fail_count") or 0) + 1
                if reason == "rate-limit":
                    await asyncio.to_thread(lambda: _cooldown(conn, r["account_id"], COOLDOWN_RATE, "rate-limit"))
                elif reason == "auth":
                    # Bad credentials/banned -> quarantine immediately
                    await asyncio.to_thread(lambda: _quarantine(conn, r["account_id"], "auth"))
                else:  # network/transient
                    if fails >= QUARANTINE_FAILS:
                        await asyncio.to_thread(lambda: _quarantine(conn, r["account_id"], "repeated-failures"))
                    else:
                        await asyncio.to_thread(lambda: _cooldown(conn, r["account_id"], COOLDOWN_BAD, "network"))
        return

    await asyncio.gather(*[_check_one(r) for r in to_check])


async def _ensure_rate_buckets():
    rl = SqliteTokenBucketLimiter()
    await rl.ensure_bucket(RATE_BUCKET_NAME, capacity=RATE_BUCKET_CAPACITY, refill_rate=RATE_BUCKET_REFILL)


async def main():
    load_dotenv()
    print(f"[account_pool_manager] Starting. DB={ACCOUNTS_DB}, proxies={PROXIES_JSON}, interval={INTERVAL}s")

    conn = _connect_db()
    global _proxy_list
    _proxy_list = _load_proxies(PROXIES_JSON)

    # Prometheus endpoint
    try:
        start_http_server(PROM_PORT)
        print(f"[account_pool_manager] Prometheus metrics on :{PROM_PORT}")
    except Exception as e:
        print(f"[account_pool_manager] WARN: failed to start Prometheus server: {e}")

    # Ensure base rate-limiter buckets
    await _ensure_rate_buckets()

    cycle = 0
    while not _shutdown:
        cycle += 1
        try:
            await _maintain_accounts(conn)
            print(f"[account_pool_manager] Cycle {cycle} complete. ready={g_accounts_ready._value.get()}, cooling={g_accounts_cooling._value.get()}, leased={g_accounts_leased._value.get()}, quarantine={g_accounts_quarantine._value.get()}")
        except Exception as e:
            print(f"[account_pool_manager] ERROR in cycle {cycle}: {e}")

        # Sleep with respond-to-shutdown
        slept = 0
        while slept < INTERVAL and not _shutdown:
            await asyncio.sleep(2)
            slept += 2

    print("[account_pool_manager] Exiting.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[account_pool_manager] KeyboardInterrupt. Exiting.")
