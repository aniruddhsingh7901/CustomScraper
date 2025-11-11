#!/usr/bin/env python3
"""
Worker Orchestrator for Reddit Scraping

Purpose
- Central async orchestrator that runs 24/7 (typically under PM2)
- Manages:
  - Account allocation (75% of available accounts as active workers)
  - Proxy rotation (via AccountPool -> ProxyPool)
  - Job distribution (from scraping/config/scraping_config.json)
  - Automatic recovery from rate limits, bans, and failures
  - Checkpoints (via Checkpointer inside scrape_advanced)
  - Job cooldown (20–30 minutes) between refresh cycles

Design Constraints
- No Redis/Kafka; jobs are read directly from JSON config
- Account and checkpoint state in SQLite as implemented elsewhere
- Headers-based rate-limit detection when feasible; fallback on exception heuristics

Run
- PM2-managed or python invocation
- Exposes logs; Prometheus metrics are handled by account_pool_manager.py

Env knobs
- REDDIT_ACCOUNTS_DB: storage/reddit/accounts.db
- REDDIT_PROXIES_JSON: storage/reddit/proxies.json
- ORCH_CONFIG_PATH: scraping/config/scraping_config.json
- ORCH_JOB_STATE_JSON: storage/reddit/job_state.json  (job cooldown tracking)
- ORCH_POLL_SECONDS: 60   (refresh config)
- ORCH_IDLE_SLEEP:   300  (when no jobs)
- ORCH_JOB_COOLDOWN_MIN: 1200  (20 minutes)
- ORCH_JOB_COOLDOWN_MAX: 1800  (30 minutes)
- ORCH_ENTITY_LIMIT: 200  (per job scrape_advanced target of items)
"""

import asyncio
import json
import os
import random
import signal
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure repo root in sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

import bittensor as bt
import asyncpraw
from common.data import DataEntity, DataLabel
from common.date_range import DateRange

from scraping.scraper import ScrapeConfig
from scraping.reddit.options import RedditScrapeOptions, CommentHarvestMode, ListingType, TimeFilter, SortMode
from scraping.reddit.reddit_custom_scraper import RedditCustomScraper
from scraping.reddit.session_pool import AccountPool, AccountLease
from scraping.reddit.checkpointer import Checkpointer
from scraping.reddit.worker_checkpoint_store import WorkerCheckpointStore
from scraping.reddit.model import RedditContent


# Defaults / env ----------------------------------------------------------------

ACCOUNTS_DB = os.environ.get("REDDIT_ACCOUNTS_DB", "storage/reddit/accounts.db")
PROXIES_JSON = os.environ.get("REDDIT_PROXIES_JSON", "storage/reddit/proxies.json")

CONFIG_PATH = os.environ.get("ORCH_CONFIG_PATH", "scraping/config/scraping_config.json")
JOB_STATE_JSON = os.environ.get("ORCH_JOB_STATE_JSON", "storage/reddit/job_state.json")

POLL_SECONDS = int(os.environ.get("ORCH_POLL_SECONDS", "60"))
IDLE_SLEEP = int(os.environ.get("ORCH_IDLE_SLEEP", "300"))
JOB_COOLDOWN_MIN = int(os.environ.get("ORCH_JOB_COOLDOWN_MIN", "1200"))  # 20 min
JOB_COOLDOWN_MAX = int(os.environ.get("ORCH_JOB_COOLDOWN_MAX", "1800"))  # 30 min
ENTITY_LIMIT = int(os.environ.get("ORCH_ENTITY_LIMIT", "200"))

# Globals ----------------------------------------------------------------------

_shutdown = False

def _handle_signal(signum, frame):
    global _shutdown
    _shutdown = True
    print(f"[worker_orchestrator] Received signal {signum}; shutting down...")

signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# Helpers ----------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)

def _parse_iso8601(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        try:
            base = s.split(".")[0]
            if base.endswith("Z"):
                base = base[:-1]
            return datetime.fromisoformat(base).replace(tzinfo=timezone.utc)
        except Exception:
            return None

def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)

def _job_cooldown_window() -> int:
    return random.randint(JOB_COOLDOWN_MIN, JOB_COOLDOWN_MAX)

def _filter_reddit_jobs(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    for entry in cfg.get("scraper_configs", []):
        if entry.get("scraper_id") == "Reddit.custom":
            jobs.extend(entry.get("jobs", []) or [])
    return jobs

def _job_ready(job: Dict[str, Any], state: Dict[str, Any]) -> bool:
    jid = job.get("id")
    st = state.get(jid) or {}
    next_ts = st.get("next_eligible_ts", 0)
    return time.time() >= float(next_ts or 0)

def _mark_job_cooldown(job: Dict[str, Any], state: Dict[str, Any]) -> None:
    jid = job.get("id")
    st = state.get(jid) or {}
    st["last_run_ts"] = time.time()
    st["next_eligible_ts"] = st["last_run_ts"] + _job_cooldown_window()
    state[jid] = st

def _weighted_choice(jobs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not jobs:
        return None
    weights = [float(j.get("weight", 1.0) or 1.0) for j in jobs]
    try:
        return random.choices(jobs, weights=weights, k=1)[0]
    except Exception:
        return random.choice(jobs)

def _build_scrape_config(job: Dict[str, Any]) -> ScrapeConfig:
    params = job.get("params", {}) or {}
    label = params.get("label")
    start = _parse_iso8601(params.get("post_start_datetime")) or (_utc_now() - (datetime.now() - datetime.now()))  # fallback UTC now if None
    end = _parse_iso8601(params.get("post_end_datetime")) or _utc_now()
    # If both are None, use a safe default: last 7 days
    if not params.get("post_start_datetime") and not params.get("post_end_datetime"):
        end = _utc_now()
        start = end - (end - end.replace(hour=0))
    dr = DateRange(start=start, end=end)
    labels = [DataLabel(value=label)] if label else None
    return ScrapeConfig(
        entity_limit=ENTITY_LIMIT,
        date_range=dr,
        labels=labels,
    )

def _build_options(job: Dict[str, Any]) -> RedditScrapeOptions:
    # Defaults: scrape submissions, include all comments with throttling/depth guard
    # Use safe defaults; these fields exist in RedditScrapeOptions.
    return RedditScrapeOptions(
        dedupe_on_uri=True,
        pagination_target=ENTITY_LIMIT,
        include_comments=True,
        harvest_mode=CommentHarvestMode.ALL_COMMENTS,
        expand_comment_depth_limit=10,  # safety
        listing=ListingType.NEW,
        time_filter=TimeFilter.ALL,
        sort=SortMode.NEW,
    )

def _looks_rate_limited(msg: str) -> bool:
    s = msg.lower()
    return ("too many requests" in s) or ("ratelimit" in s) or ("429" in s)

def _looks_auth_ban(msg: str) -> bool:
    s = msg.lower()
    return ("unauthorized" in s) or ("forbidden" in s) or ("403" in s) or ("401" in s) or ("invalid_grant" in s)

def _extract_last_ids(entities: List[DataEntity]) -> Tuple[Optional[str], Optional[str]]:
    """
    Derive the last seen post/comment fullname IDs from scraped DataEntity list.
    Uses RedditContent.from_data_entity to decode and inspects t3_/t1_ prefixes.
    """
    last_post_id: Optional[str] = None
    last_comment_id: Optional[str] = None
    for e in entities:
        try:
            rc = RedditContent.from_data_entity(e)
            rid = rc.id or ""
            if rid.startswith("t3_"):
                last_post_id = rid
            elif rid.startswith("t1_"):
                last_comment_id = rid
        except Exception:
            continue
    return last_post_id, last_comment_id

# Worker task -------------------------------------------------------------------

async def worker_task(worker_id: int, pool: AccountPool, jobs_cfg_path: Path, job_state_path: Path):
    scraper = RedditCustomScraper()
    checkpointer = Checkpointer()  # used by scrape_advanced implicitly
    job_state: Dict[str, Any] = _load_json(job_state_path, {})
    last_cfg_load_ts = 0
    cfg_cache: Dict[str, Any] = {}
    store = WorkerCheckpointStore()

    print(f"[worker_orchestrator] Worker-{worker_id} starting")

    while not _shutdown:
        try:
            # Periodically reload job config
            if time.time() - last_cfg_load_ts >= POLL_SECONDS or not cfg_cache:
                cfg_cache = _load_json(jobs_cfg_path, {})
                last_cfg_load_ts = time.time()

            # Filter ready jobs
            all_jobs = _filter_reddit_jobs(cfg_cache)
            ready_jobs = [j for j in all_jobs if _job_ready(j, job_state)]

            if not ready_jobs:
                # Nothing to do; sleep a while
                await asyncio.sleep(IDLE_SLEEP)
                continue

            # Choose a job (weighted)
            job = _weighted_choice(ready_jobs)
            if job is None:
                await asyncio.sleep(5)
                continue

            # Acquire account lease
            lease: Optional[AccountLease] = None
            try:
                lease = await pool.acquire()
            except Exception as e:
                print(f"[worker_orchestrator] Worker-{worker_id} no accounts ready: {e}")
                await asyncio.sleep(10)
                continue

            # Build configs
            scrape_config = _build_scrape_config(job)
            options = _build_options(job)
            # Initial checkpoint write (account + subreddit), IDs unknown yet
            last_subreddit = scrape_config.labels[0].value if scrape_config.labels else "all"
            try:
                await store.upsert(
                    worker_id=f"{worker_id}",
                    account_id=(lease.account_id if lease else None),
                    last_subreddit=last_subreddit,
                    last_post_id=None,
                    last_comment_id=None,
                )
            except Exception:
                pass

            # Run scrape with account+proxy via pool
            try:
                entities: List[DataEntity] = await scraper.scrape_advanced(
                    scrape_config=scrape_config,
                    options=options,
                    pool=pool,
                )
                # Mark job cooldown and persist job state
                _mark_job_cooldown(job, job_state)
                _save_json(job_state_path, job_state)
                # Persist worker checkpoint with last processed IDs
                try:
                    lp, lc = _extract_last_ids(entities)
                    await store.upsert(
                        worker_id=f"{worker_id}",
                        account_id=(lease.account_id if lease else None),
                        last_subreddit=last_subreddit,
                        last_post_id=lp,
                        last_comment_id=lc,
                    )
                except Exception:
                    pass
                print(f"[worker_orchestrator] Worker-{worker_id} job {job.get('id')} scraped {len(entities)} entities.")
                # Release lease with success
                if lease is not None:
                    await lease.release(success=True)

            except Exception as e:
                msg = str(e)
                print(f"[worker_orchestrator] Worker-{worker_id} error on job {job.get('id')}: {msg}")
                # Heuristic-based rate-limit/auth handling
                try:
                    if lease is not None:
                        if _looks_rate_limited(msg):
                            await pool.cooldown(lease, seconds=120, reason="rate-limit")
                            await lease.release(success=False)
                        elif _looks_auth_ban(msg):
                            await pool.quarantine(lease, reason="auth")
                            await lease.release(success=False)
                        else:
                            await lease.release(success=False)
                except Exception:
                    pass
                # Update checkpoint on error (at least account/subreddit known)
                try:
                    await store.upsert(
                        worker_id=f"{worker_id}",
                        account_id=(lease.account_id if lease else None),
                        last_subreddit=(last_subreddit if 'last_subreddit' in locals() else None),
                        last_post_id=None,
                        last_comment_id=None,
                    )
                except Exception:
                    pass
                # Backoff briefly and retry loop
                await asyncio.sleep(10)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[worker_orchestrator] Worker-{worker_id} unexpected error: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(5)

    print(f"[worker_orchestrator] Worker-{worker_id} exiting.")


# Orchestrator main loop --------------------------------------------------------

async def orchestrate():
    load_dotenv()
    jobs_cfg_path = Path(CONFIG_PATH)
    job_state_path = Path(JOB_STATE_JSON)

    pool = AccountPool(db_path=ACCOUNTS_DB, proxies_path=PROXIES_JSON)

    # Worker registry
    workers: Dict[int, asyncio.Task] = {}
    next_worker_id = 0

    print(f"[worker_orchestrator] Starting. cfg={jobs_cfg_path} job_state={job_state_path}")

    while not _shutdown:
        try:
            # Determine number of active accounts
            try:
                health = await pool.health_report()
            except Exception as e:
                print(f"[worker_orchestrator] Failed to read health_report: {e}")
                health = {}
            ready = int(health.get("ready", 0))
            leased = int(health.get("leased", 0))
            quarantine = int(health.get("quarantine", 0))

            # Active worker target: 75% of available accounts
            target_workers = max(0, int(ready * 0.75))
            current_workers = len(workers)

            # Scale up
            if target_workers > current_workers:
                add = target_workers - current_workers
                for _ in range(add):
                    wid = next_worker_id
                    next_worker_id += 1
                    task = asyncio.create_task(worker_task(wid, pool, jobs_cfg_path, job_state_path), name=f"reddit-worker-{wid}")
                    workers[wid] = task
                    print(f"[worker_orchestrator] Spawned worker-{wid}; total={len(workers)}")

            # Scale down (cancel extra)
            if target_workers < current_workers:
                to_cancel = current_workers - target_workers
                for wid, task in list(workers.items()):
                    if to_cancel <= 0:
                        break
                    task.cancel()
                    try:
                        await task
                    except Exception:
                        pass
                    workers.pop(wid, None)
                    to_cancel -= 1
                    print(f"[worker_orchestrator] Stopped worker-{wid}; total={len(workers)}")

            # Reap dead tasks
            for wid, task in list(workers.items()):
                if task.done():
                    workers.pop(wid, None)
                    print(f"[worker_orchestrator] Worker-{wid} ended; removing. total={len(workers)}")

            # Sleep before next orchestration tick
            await asyncio.sleep(POLL_SECONDS)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[worker_orchestrator] Orchestrator loop error: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(5)

    print("[worker_orchestrator] Shutting down; cancelling workers...")
    for wid, task in list(workers.items()):
        task.cancel()
        try:
            await task
        except Exception:
            pass
    print("[worker_orchestrator] Exit.")

# Entrypoint -------------------------------------------------------------------

async def main():
    await orchestrate()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[worker_orchestrator] KeyboardInterrupt; exiting.")
