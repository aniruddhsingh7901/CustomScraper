RedditScraper data stores and metrics: layout, schemas, and flow

Overview
This system uses:
- JSON files for queue/proxies input where required
- SQLite for durable state (accounts/session pool, checkpoints, rate limiter)
- Prometheus metrics (not a DB table; exposed in-process for scraping)

Stores by component

1) Session Pool (Accounts + Proxies DB)
- File: storage/reddit/accounts.db (override with REDDIT_ACCOUNTS_DB)
- Tables:
  - accounts
    - account_id TEXT PRIMARY KEY
    - client_id TEXT NOT NULL
    - client_secret TEXT NOT NULL
    - username TEXT NOT NULL
    - password TEXT NOT NULL
    - status TEXT NOT NULL DEFAULT 'ready'       -- ready | leased | quarantine
    - cooldown_until REAL DEFAULT 0
    - fail_count INTEGER NOT NULL DEFAULT 0
    - last_error TEXT
    - proxy_id TEXT                               -- optional binding if you later do 1:1
  - proxies
    - proxy_id TEXT PRIMARY KEY
    - http TEXT
    - https TEXT
    - tag TEXT
    - provider TEXT
- How it works:
  - AccountPool.acquire() selects a ready account (respects cooldown/quarantine)
  - ProxyPool rotates proxies (from JSON) per lease by default
  - Lease returns asyncpraw client configured with proxy; release() cools down

2) Proxies input (JSON and optional DB mirror)
- Source input file (you edit): scraping/reddit/proxy.txt
  - host:port:user:pass per line
- Generated runtime file: storage/reddit/proxies.json (override REDDIT_PROXIES_JSON)
  - [{"http": "http://user:pass@host:port", "https": "http://user:pass@host:port"}, ...]
- Optional: proxies are also mirrored into SQLite proxies table for visibility by running:
  - python scripts/seed_reddit_pool.py
- Rotation uses JSON pool; DB proxies table is for auditing/inspection unless you enable 1:1 mapping.

3) Checkpoints (SQLite)
- File: storage/reddit/checkpoints.db (override REDDIT_CHECKPOINTS_DB)
- Table:
  - checkpoints
    - job_id TEXT PRIMARY KEY
    - payload TEXT NOT NULL            -- JSON payload
    - updated_at REAL NOT NULL         -- epoch seconds
- API: scraping/reddit/checkpointer.py (Checkpointer)
  - save_progress(job_id, checkpoint_dict)
  - load_progress(job_id) -> dict | None
- What we store:
  - seen_ids: [t3_/t1_ fullname IDs]
  - seen_urls: [canonical urls]
  - last_timestamp
  - Additional per-job fields (e.g., last_submission_id) may be added by callers
- Resume:
  - scrape_advanced() loads checkpoint for a deterministic key derived from subreddit + date_range + options and skips already-seen items.

4) Rate Limiter (SQLite token bucket)
- File: storage/reddit/ratelimiter.db (override REDDIT_RATE_DB)
- Table:
  - buckets
    - bucket TEXT PRIMARY KEY
    - capacity REAL
    - tokens REAL
    - refill_rate REAL
    - updated_at REAL
- API: scraping/reddit/rate_limiter.py (SqliteTokenBucketLimiter)
  - ensure_bucket(name, capacity, refill_rate)
  - acquire(name, tokens=1.0, timeout=None) -> bool
- Usage:
  - Used to gate heavy comment-tree expansions (replace_more) with a global bucket
  - You can add more buckets for other endpoints if needed

5) Job Queue (JSON)
- File: storage/reddit/jobs.json (override REDDIT_JOBS_JSON)
- Structure:
  {
    "queue": [ {id, weight, payload, attempts, enqueued_at}, ... ],
    "inflight": { "job_id": {job}, ... }
  }
- API: scraping/reddit/job_queue.py
  - enqueue, dequeue, ack, nack, reprioritize, size
- Semantics:
  - Weighted scheduling with simple aging
  - Small, retryable work units; not coupled to SQLite

6) Deduplication
- Current implementation:
  - In-memory sets of seen_ids and seen_urls during a run
  - Persisted via checkpoint payload (seen_ids/seen_urls) to resume across runs
- Optional future: a dedicated SQLite dedup table (not required at present)
  - Would be storage/reddit/dedup.db with a keys table
  - For now, checkpoint payload is sufficient and simpler

7) Metrics (Prometheus, not SQLite)
- No “metrics table” in SQLite; metrics are in-process counters/gauges/histograms
- Definitions: scraping/reddit/metrics.py
  - Gauges: reddit_active_accounts, reddit_accounts_cooldown, reddit_replace_more_inflight
  - Counters: reddit_requests_total{endpoint}, reddit_items_scraped_total{type,subreddit}, reddit_account_errors_total{kind}, reddit_proxy_failures_total{kind}
  - Histogram: reddit_replace_more_time_seconds
- How to consume:
  - If you have an HTTP server exposing /metrics, Prometheus scrapes it
  - This repo includes prometheus_client; you can wire an endpoint in your runner to expose metrics
  - Alternatively, pushgateway or custom exporter can be integrated
- Why not a metrics table:
  - Prometheus model favors a time-series pull; storing metrics in SQLite is atypical
  - If you want a DB log, add a lightweight audit logger that writes roll-ups to SQLite or S3

Operational notes and commands

Inspect SQLite state
- Accounts status:
  sqlite3 storage/reddit/accounts.db "SELECT status, COUNT(*) FROM accounts GROUP BY status;"
- Sample accounts:
  sqlite3 storage/reddit/accounts.db "SELECT account_id, username, status, fail_count FROM accounts LIMIT 10;"
- Proxies table (if mirrored):
  sqlite3 storage/reddit/accounts.db "SELECT COUNT(*) FROM proxies;"
  sqlite3 storage/reddit/accounts.db "SELECT proxy_id, substr(http,1,40) FROM proxies LIMIT 5;"
- Checkpoints:
  sqlite3 storage/reddit/checkpoints.db "SELECT job_id, length(payload), updated_at FROM checkpoints LIMIT 5;"
- Rate limiter buckets:
  sqlite3 storage/reddit/ratelimiter.db "SELECT bucket, capacity, tokens, refill_rate FROM buckets;"

Seeding and updates
- Input files you edit:
  - scraping/reddit/redditaccount.txt (username:password:client_id:client_secret)
  - scraping/reddit/proxy.txt (host:port:user:pass)
- Seed command:
  - python scripts/seed_reddit_pool.py
- Effects:
  - Upserts accounts into storage/reddit/accounts.db
  - Regenerates storage/reddit/proxies.json
  - Optionally mirrors proxies into SQLite proxies table for visibility

Proxy policy
- Current: rotating per lease (pooled) — each acquire() picks next healthy proxy
- 1:1 binding (optional later): populate accounts.proxy_id and change acquire() to prefer bound proxy

FAQ

Q: Why is the proxies DB table empty?
A: Rotation uses proxies.json by default. If you want visibility in SQLite, re-run the seeder (updated) which mirrors proxies into the proxies table. This does not change rotation behavior unless you implement 1:1 proxy binding.

Q: Is there a “metrics table”?
A: No. Metrics are Prometheus time-series exported from process memory. Use a metrics endpoint for Prometheus to scrape. We can add a SQLite audit log if you explicitly want a table.

Q: Are checkpoints in the same DB as accounts?
A: No. They have a separate DB (storage/reddit/checkpoints.db) to keep responsibilities clear and to avoid lock contention with session leasing.

Q: Can we store dedup state in SQLite?
A: Presently we persist dedup through checkpoint payload (seen_ids/seen_urls). If you need a global dedup across jobs, we can add a dedicated SQLite dedup store.

Where code lives
- Session pool: scraping/reddit/session_pool.py
- Checkpointer: scraping/reddit/checkpointer.py
- Job queue: scraping/reddit/job_queue.py
- Rate limiter: scraping/reddit/rate_limiter.py
- Metrics: scraping/reddit/metrics.py
- Scraper: scraping/reddit/reddit_custom_scraper.py (scrape_advanced uses these components)

This layout follows your constraint: JSON where required, and SQLite for account pool and checkpoint/worker management, with Prometheus metrics for observability rather than a DB table.
