#!/usr/bin/env python3
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

# Ensure repo root on sys.path when running as a script (so 'scraping' package is importable)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraping.reddit.session_pool import AccountPool, AccountCredential, ProxyConfig


ACCOUNTS_TXT_DEFAULT = "scraping/reddit/redditaccount.txt"
PROXIES_TXT_DEFAULT = "scraping/reddit/proxy.txt"
ACCOUNTS_DB_DEFAULT = os.getenv("REDDIT_ACCOUNTS_DB", "storage/reddit/accounts.db")
PROXIES_JSON_DEFAULT = os.getenv("REDDIT_PROXIES_JSON", "storage/reddit/proxies.json")


def parse_accounts_line(line: str) -> Tuple[str, str, str, str]:
    """
    Parse a single line in the format:
      username:password:client_id:client_secret
    Handles stray tabs/spaces around fields and in client_id.

    Strategy:
      - Split by ":" then:
        username = parts[0].strip()
        password = parts[1].strip()
        client_secret = parts[-1].strip()
        client_id = ":".join(parts[2:-1]).strip()  (join middle segments, then strip)
      - Collapse whitespace inside client_id (e.g. '166 WGL...' -> '166WGL...')
    """
    parts = line.strip().split(":")
    if len(parts) < 4:
        raise ValueError(f"Invalid account line (need 4 fields): {line!r}")

    username = parts[0].strip()
    password = parts[1].strip()
    client_secret = parts[-1].strip()
    middle = ":".join(parts[2:-1]).strip()

    # Normalize whitespace in client_id
    client_id = re.sub(r"\s+", "", middle)

    if not username or not password or not client_id or not client_secret:
        raise ValueError(f"Empty field in account line: {line!r}")

    return username, password, client_id, client_secret


def parse_proxy_line(line: str) -> Tuple[str, str, str, str]:
    """
    Parse a proxy line: host:port:user:pass
    Returns (host, port, user, pwd).
    """
    parts = line.strip().split(":")
    if len(parts) != 4:
        raise ValueError(f"Invalid proxy line (need 4 fields host:port:user:pass): {line!r}")
    host, port, user, pwd = [p.strip() for p in parts]
    if not host or not port or not user or not pwd:
        raise ValueError(f"Empty field in proxy line: {line!r}")
    return host, port, user, pwd


async def seed_accounts(pool: AccountPool, accounts_path: Path) -> int:
    if not accounts_path.exists():
        print(f"[seed] accounts file not found: {accounts_path}")
        return 0

    inserted = 0
    lines = accounts_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            username, password, client_id, client_secret = parse_accounts_line(line)
            account_id = f"acct-{username}"
            cred = AccountCredential(
                client_id=client_id,
                client_secret=client_secret,
                username=username,
                password=password,
            )
            await pool.add_account(account_id, cred)
            inserted += 1
        except Exception as e:
            print(f"[seed][accounts] skip line due to error: {e} | line={raw!r}")
            continue
    return inserted


def write_proxies_json(proxies_txt: Path, out_json: Path) -> int:
    if not proxies_txt.exists():
        print(f"[seed] proxies file not found: {proxies_txt}")
        return 0

    out_json.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    items: List[dict] = []
    lines = proxies_txt.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            host, port, user, pwd = parse_proxy_line(line)
            auth = f"{user}:{pwd}"
            url = f"http://{auth}@{host}:{port}"
            items.append({"http": url, "https": url})
            count += 1
        except Exception as e:
            print(f"[seed][proxies] skip line due to error: {e} | line={raw!r}")
            continue

    with out_json.open("w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    return count


async def seed_proxies_db(pool: AccountPool, proxies_txt: Path) -> int:
    """
    Also seed proxies into the SQLite proxies table for visibility/auditing.
    Rotation still uses JSON by default; DB is optional.
    """
    if not proxies_txt.exists():
        return 0
    inserted = 0
    lines = proxies_txt.read_text(encoding="utf-8", errors="ignore").splitlines()
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            host, port, user, pwd = parse_proxy_line(line)
            auth = f"{user}:{pwd}"
            url = f"http://{auth}@{host}:{port}"
            proxy = ProxyConfig(http=url, https=url)
            proxy_id = f"proxy-{idx:04d}-{host}-{port}"
            # sanitize proxy_id (remove illegal chars just in case)
            proxy_id = proxy_id.replace(":", "_").replace("/", "_")
            await pool.add_proxy(proxy_id, proxy)
            inserted += 1
        except Exception as e:
            print(f"[seed][proxies-db] skip line due to error: {e} | line={raw!r}")
            continue
    return inserted


async def main():
    accounts_txt = Path(os.environ.get("REDDIT_ACCOUNTS_TXT", ACCOUNTS_TXT_DEFAULT))
    proxies_txt = Path(os.environ.get("REDDIT_PROXIES_TXT", PROXIES_TXT_DEFAULT))
    accounts_db = os.environ.get("REDDIT_ACCOUNTS_DB", ACCOUNTS_DB_DEFAULT)
    proxies_json = os.environ.get("REDDIT_PROXIES_JSON", PROXIES_JSON_DEFAULT)

    print(f"[seed] accounts txt: {accounts_txt}")
    print(f"[seed] proxies txt:  {proxies_txt}")
    print(f"[seed] accounts db:  {accounts_db}")
    print(f"[seed] proxies json: {proxies_json}")

    pool = AccountPool(db_path=accounts_db, proxies_path=proxies_json)
    acc_count = await seed_accounts(pool, accounts_txt)
    print(f"[seed] accounts inserted/updated: {acc_count}")

    prox_count = write_proxies_json(proxies_txt, Path(proxies_json))
    print(f"[seed] proxies written: {prox_count}")

    # Optional: mirror proxies into SQLite for visibility
    db_prox_count = await seed_proxies_db(pool, proxies_txt)
    print(f"[seed] proxies inserted into DB: {db_prox_count}")

    # Health report (accounts)
    report = await pool.health_report()
    print(f"[seed] account health report: {report}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
