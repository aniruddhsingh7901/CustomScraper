module.exports = {
  apps: [
    {
      name: "dd-fetcher",
      cwd: "/root/data-universe",
      // Run a persistent bash loop that executes the Python fetcher every 30 minutes
      script: "/bin/bash",
      args: [
        "-lc",
        "while true; do /root/data-universe/.venv/bin/python scripts/fetch_dynamic_desirability.py --wallet.name An-13 --wallet.hotkey An-1 --subtensor.network finney --netuid 13 --vpermit_rao_limit 10000 || true; sleep 1800; done"
      ],
      autorestart: true,
      watch: false,
      time: true,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "reddit-account-manager",
      cwd: "/home/anirudh/CustomScraper",
      // Long-running account pool manager: maintains accounts/proxies/rate-limiter state in SQLite and exposes Prometheus metrics
      script: "/bin/bash",
      args: [
        "-lc",
        "python scripts/account_pool_manager.py"
      ],
      autorestart: true,
      watch: false,
      time: true,
      env: {
        PYTHONUNBUFFERED: "1",
        // Paths for state stores
        "REDDIT_ACCOUNTS_DB": "storage/reddit/accounts.db",
        "REDDIT_PROXIES_JSON": "storage/reddit/proxies.json",
        // Prometheus metrics port
        "PROM_PORT": "9108",
        // Maintenance cadence and policies
        "ACCOUNT_MANAGER_INTERVAL": "60",
        "ACCOUNT_MANAGER_COOLDOWN_BAD": "60",
        "ACCOUNT_MANAGER_COOLDOWN_RATE": "120",
        "ACCOUNT_MANAGER_QUARANTINE_FAILS": "5",
        // Global rate limiter bucket defaults
        "RATE_BUCKET_NAME": "replace_more",
        "RATE_BUCKET_CAPACITY": "5.0",
        "RATE_BUCKET_REFILL": "2.0"
      }
    },
    {
      name: "reddit-orchestrator",
      cwd: "/home/anirudh/CustomScraper",
      // 24/7 orchestrator: spawns workers at ~75% of ready accounts, distributes jobs from JSON, handles cooldowns/checkpoints
      script: "/bin/bash",
      args: [
        "-lc",
        "python -u scraping/reddit/worker_orchestrator.py"
      ],
      autorestart: true,
      watch: false,
      time: true,
      env: {
        PYTHONUNBUFFERED: "1",
        "REDDIT_ACCOUNTS_DB": "storage/reddit/accounts.db",
        "REDDIT_PROXIES_JSON": "storage/reddit/proxies.json",
        "ORCH_CONFIG_PATH": "scraping/config/scraping_config.json",
        "ORCH_JOB_STATE_JSON": "storage/reddit/job_state.json",
        "ORCH_POLL_SECONDS": "60",
        "ORCH_IDLE_SLEEP": "300",
        "ORCH_JOB_COOLDOWN_MIN": "1200",
        "ORCH_JOB_COOLDOWN_MAX": "1800",
        "ORCH_ENTITY_LIMIT": "200"
      }
    }
  ]
};
