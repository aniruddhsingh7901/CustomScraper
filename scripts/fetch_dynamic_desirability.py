#!/usr/bin/env python3
"""
Fetches the latest Dynamic Desirability aggregate (total.json) by reading validator
commitments from chain and aggregating their preference JSONs.

This script is intended to be run by PM2 on a schedule. It will:
- Build a bittensor config (wallet/subtensor/logging + netuid, vpermit_rao_limit)
- Run the retrieval pipeline which writes dynamic_desirability/total.json
- Exit

Usage examples:
  python scripts/fetch_dynamic_desirability.py \
    --wallet.name An-13 --wallet.hotkey An-1 \
    --subtensor.network finney --netuid 13 --vpermit_rao_limit 10000
"""

import asyncio
import os
import sys
import traceback
import json
from datetime import datetime, timedelta
import bittensor as bt


def _sort_jobs_by_platform_weight(total_jobs):
    """Return jobs sorted with platform order reddit, x, youtube and by descending weight; unique by id."""
    if not total_jobs:
        return []
    # Dedup by id (keep highest weight if duplicate ids)
    best_by_id = {}
    for job in total_jobs:
        jid = job.get("id")
        weight = job.get("weight", 0)
        if jid is None:
            continue
        prev = best_by_id.get(jid)
        if prev is None or weight > prev.get("weight", 0):
            best_by_id[jid] = job
    jobs = list(best_by_id.values())
    platform_order = {"reddit": 0, "x": 1, "youtube": 2}
    def key_fn(j):
        params = j.get("params", {}) or {}
        plat = params.get("platform")
        w = j.get("weight", 0)
        try:
            w_val = float(w)
        except Exception:
            w_val = 0.0
        return (platform_order.get(plat, 99), -w_val, j.get("id", ""))
    jobs.sort(key=key_fn)
    return jobs


def _platform_for_scraper_id(scraper_id: str | None) -> str | None:
    if not scraper_id:
        return None
    if scraper_id == "Reddit.custom" or (isinstance(scraper_id, str) and scraper_id.startswith("Reddit.")):
        return "reddit"
    if scraper_id == "X.apidojo" or (isinstance(scraper_id, str) and scraper_id.startswith("X.")):
        return "x"
    if scraper_id == "YouTube.custom.transcript" or (isinstance(scraper_id, str) and scraper_id.startswith("YouTube.")):
        return "youtube"
    return None


def _split_by_platform(jobs: list[dict]) -> dict[str, list[dict]]:
    buckets = {"reddit": [], "x": [], "youtube": []}
    for j in jobs or []:
        params = j.get("params") or {}
        plat = params.get("platform")
        if plat in buckets:
            buckets[plat].append(j)
    return buckets


def _merge_and_sort_jobs(old_jobs: list[dict], new_jobs: list[dict]) -> list[dict]:
    """Append new jobs and keep past jobs. If id already exists, update with new entry. Sort by weight desc then id asc."""
    by_id: dict[str, dict] = {}
    for j in old_jobs or []:
        jid = j.get("id")
        if jid is not None:
            by_id[jid] = j
    for j in new_jobs or []:
        jid = j.get("id")
        if jid is not None:
            by_id[jid] = j  # overwrite/update with latest job payload
    merged = list(by_id.values())
    def w(j):
        try:
            return float(j.get("weight", 0.0))
        except Exception:
            return 0.0
    merged.sort(key=lambda j: (-w(j), j.get("id", "")))
    return merged


def _read_existing_jobs_and_cadence(scraping_config_path: str):
    """Reads existing scraping_config.json and returns (existing_jobs_by_platform, cadence_map, passthrough_scrapers, base_cfg_dict_flag)."""
    default_cadence = {"reddit": 60, "x": 300, "youtube": 100}
    existing_jobs = {"reddit": [], "x": [], "youtube": []}
    cadence = default_cadence.copy()
    passthrough_scrapers = []
    base_cfg_dict = True

    try:
        with open(scraping_config_path, "r") as f:
            cfg = json.load(f)
    except Exception:
        return existing_jobs, cadence, passthrough_scrapers, False

    if isinstance(cfg, list):
        # Flat jobs list form (from previous runs) -> split by platform
        existing_jobs = _split_by_platform(cfg)
        base_cfg_dict = False
        return existing_jobs, cadence, passthrough_scrapers, base_cfg_dict

    if not isinstance(cfg, dict):
        return existing_jobs, cadence, passthrough_scrapers, False

    base_cfg_dict = True
    # Iterate scraper_configs
    for sc in cfg.get("scraper_configs", []):
        sid = sc.get("scraper_id")
        plat = _platform_for_scraper_id(sid)
        if plat in existing_jobs:
            # cadence
            if isinstance(sc.get("cadence_seconds"), int):
                cadence[plat] = sc["cadence_seconds"]
            # jobs array if present
            if isinstance(sc.get("jobs"), list):
                # ensure they are dicts with params having platform; if not, we add platform based on scraper id
                normalized = []
                for j in sc["jobs"]:
                    if isinstance(j, dict):
                        params = j.get("params") or {}
                        if not params.get("platform"):
                            params = {**params, "platform": plat}
                            j = {**j, "params": params}
                        normalized.append(j)
                existing_jobs[plat] = normalized
        else:
            # Keep non-target scrapers unchanged
            passthrough_scrapers.append(sc)

    return existing_jobs, cadence, passthrough_scrapers, base_cfg_dict


def _write_scraping_config(scraping_config_path: str,
                           cadence: dict[str, int],
                           jobs_by_platform: dict[str, list[dict]],
                           passthrough_scrapers: list[dict]):
    """Writes scraper_configs with jobs array per platform, preserves passthrough scrapers."""
    platform_to_scraper = {
        "reddit": "Reddit.custom",
        "x": "X.apidojo",
        "youtube": "YouTube.custom.transcript",
    }
    # Build target scraper entries in order
    scraper_configs = []
    for plat in ["reddit", "x", "youtube"]:
        sc = {
            "scraper_id": platform_to_scraper[plat],
            "jobs": jobs_by_platform.get(plat, []),
        }
        scraper_configs.append(sc)
    # Append passthrough scrapers after our main three
    scraper_configs.extend(passthrough_scrapers or [])

    cfg_out = {"scraper_configs": scraper_configs}
    tmp_path = scraping_config_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(cfg_out, f, indent=4)
    os.replace(tmp_path, scraping_config_path)


def _append_change_log(changes_log_path: str, old_labels: dict[str, list[str]], new_labels: dict[str, list[str]]):
    """Append a minimal incremental change log entry per run."""
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "changes": {}
    }
    for plat in ["reddit", "x", "youtube"]:
        old_list = old_labels.get(plat, [])
        new_list = new_labels.get(plat, [])
        added = [l for l in new_list if l not in old_list]
        removed = [l for l in old_list if l not in new_list]
        if added or removed:
            event["changes"][plat] = {"added": added, "removed": removed}
    with open(changes_log_path, "a") as f:
        f.write(json.dumps(event) + "\n")


def main() -> int:
    try:
        # Ensure project root is on sys.path so we can import local packages
        import sys as _sys, os as _os
        _ROOT_DIR = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), _os.pardir))
        if _ROOT_DIR not in _sys.path:
            _sys.path.insert(0, _ROOT_DIR)

        # Import after sys.path is adjusted
        from neurons.config import create_config, NeuronType
        from dynamic_desirability.desirability_retrieval import run_retrieval
        from dynamic_desirability.constants import AGGREGATE_JSON_PATH
        # Build a config object that includes wallet/subtensor/logging args and our defaults
        config = create_config(NeuronType.VALIDATOR)

        print("[dd-fetcher] Starting dynamic desirability retrieval...", flush=True)
        bt.logging.info("Starting Dynamic Desirability retrieval...")
        bt.logging.info(f"Network: {getattr(config, 'subtensor', {}).network if hasattr(config, 'subtensor') else 'unknown'} | "
                        f"Netuid: {getattr(config, 'netuid', 'unknown')} | "
                        f"Wallet: {getattr(config, 'wallet', {}).name if hasattr(config, 'wallet') else 'unknown'}/"
                        f"{getattr(config, 'wallet', {}).hotkey if hasattr(config, 'wallet') else 'unknown'} | "
                        f"vpermit_rao_limit: {getattr(config, 'vpermit_rao_limit', 'unknown')}")

        # Run retrieval (writes dynamic_desirability/total.json)
        asyncio.run(run_retrieval(config))

        # Report the output path and update scraping config
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
        aggregate_path = os.path.join(project_root, "dynamic_desirability", AGGREGATE_JSON_PATH)
        default_path = os.path.join(project_root, "dynamic_desirability", "default.json")
        scraping_cfg_path = os.path.join(project_root, "scraping", "config", "scraping_config.json")
        changes_log_path = os.path.join(project_root, "scraping", "config", "dd_changes.jsonl")

        # Prefer total.json; fall back to default.json if total is not present
        src_path = aggregate_path if os.path.exists(aggregate_path) else default_path
        print(f"[dd-fetcher] Using source: {src_path}", flush=True)

        if os.path.exists(src_path):
            with open(src_path, "r") as f:
                total_jobs = json.load(f)

            # Read existing jobs and cadence, then merge (append-only; update existing by id)
            existing_jobs, cadence_map, passthrough, base_cfg_dict = _read_existing_jobs_and_cadence(scraping_cfg_path)
            new_by_platform = _split_by_platform(total_jobs)

            merged_by_platform = {}
            for plat in ["reddit", "x", "youtube"]:
                merged_by_platform[plat] = _merge_and_sort_jobs(existing_jobs.get(plat, []), new_by_platform.get(plat, []))

            _write_scraping_config(scraping_cfg_path, cadence_map, merged_by_platform, passthrough)
            total_count = sum(len(v) for v in merged_by_platform.values())
            bt.logging.info(f"Updated scraping_config with {total_count} jobs across platforms (append-only merge).")
            print(f"[dd-fetcher] Updated scraping_config with {total_count} jobs (reddit={len(merged_by_platform.get('reddit', []))}, x={len(merged_by_platform.get('x', []))}, youtube={len(merged_by_platform.get('youtube', []))}).", flush=True)
            next_run = (datetime.utcnow() + timedelta(minutes=30)).isoformat() + "Z"
            print(f"[dd-fetcher] Next run scheduled at {next_run} (in 30 minutes).", flush=True)
            print("[dd-fetcher] Run complete.", flush=True)
            return 0
        else:
            bt.logging.warning(f"Run completed but {aggregate_path} not found. Check logs above for errors.")
            print(f"[dd-fetcher] WARNING: Aggregate not found at {aggregate_path}.", flush=True)
            return 1

    except Exception as e:
        print("ERROR: Dynamic Desirability fetch failed.", file=sys.stderr)
        print(str(e), file=sys.stderr)
        traceback.print_exc()
        return 2

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
