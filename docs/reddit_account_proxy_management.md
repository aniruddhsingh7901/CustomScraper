Account and Proxy Management: Services, States, Transitions, and Rate-Limit Logic

Scope
Step-by-step description of which services manage Reddit accounts and proxies, how we determine active/free/rate-limited, and exactly how state transitions occur inside this codebase. This version adds a detailed rate-limit and cooldown policy: what signals we use (headers vs heuristics), how cooldown seconds are chosen, and how global per-feature throttling works.

Key services and files
1) AccountPool (scraping/reddit/session_pool.py)
- Backend: SQLite (storage/reddit/accounts.db, override REDDIT_ACCOUNTS_DB)
- Tables:
  - accounts(account_id, client_id, client_secret, username, password, status, cooldown_until, fail_count, last_error, proxy_id)
  - proxies(proxy_id, http, https, tag, provider)  // optional mirror for visibility
- API:
  - acquire() -> AccountLease
  - release(lease, success=True|False) -> None
  - cooldown(lease, seconds, reason) -> None
  - quarantine(lease, reason) -> None
  - health_report() -> Dict[str, int]
- Account states:
  - ready: free to use; if cooldown_until > now => cooling (temporarily blocked)
  - leased: in use by a worker (AccountPool sets on acquire, cleared on release)
  - quarantine: unhealthy; not used until manually reset

2) ProxyPool (scraping/reddit/session_pool.py)
- Backend: JSON list (storage/reddit/proxies.json, override REDDIT_PROXIES_JSON)
- Rotation: pooled round-robin per lease (default)
- API:
  - acquire() -> ProxyConfig
  - report_success(proxy) / report_failure(proxy)

3) RedditClientManager (scraping/reddit/session_pool.py)
- Builds asyncpraw.Reddit per lease
- Injects proxy via requestor_kwargs={"proxies": {"http": ..., "https": ...}}

4) RateLimiter (scraping/reddit/rate_limiter.py)
- Backend: SQLite (storage/reddit/ratelimiter.db)
- Token-bucket buckets with capacity/tokens/refill_rate/updated_at
- Used to throttle costly operations globally (e.g., replace_more for comment trees)

5) Account Pool Manager (scripts/account_pool_manager.py)
- 24/7 PM2-managed service
- Probes ready accounts with a minimal API call; updates SQLite state:
  - rate-limit signals => cooldown with reason "rate-limit"
  - auth/403/401 => quarantine with reason "auth"
  - transient network error => cooldown with reason "network" (escalate to quarantine after repeated failures)
- Ensures a default global rate-limiter bucket exists
- Exposes Prometheus metrics (counts by status, actions)

Rate-limit and cooldown policy

Signals we use
- Primary (header-driven when available): Reddit typically returns x-ratelimit-remaining and x-ratelimit-reset headers. AsyncPRAW abstracts the HTTP layer, so getting headers per-call is not always straightforward in user code. Where available via exceptions or response info:
  - If remaining <= threshold and reset is provided: set cooldown to reset seconds (clamped to a reasonable max) so the account sleeps until Reddit resets tokens.
- Fallback (status/exception-driven): In practice, asyncpraw errors and messages are reliable indicators:
  - 429 / “Too Many Requests” / “RATELIMIT” -> cooldown (rate-limited)
  - 401/403 / “Unauthorized” / “Forbidden” / “invalid_grant” -> quarantine (credentials/banned)
  - Timeouts/connection errors -> cooldown; escalate to quarantine after repeated failures

Cooldown durations (configurable)
- ACCOUNT_MANAGER_COOLDOWN_RATE (default 120s)
  - Applied when we detect explicit rate-limit signals (429/RATELIMIT). If header reset is known (future enhancement), we set cooldown to that value instead.
- ACCOUNT_MANAGER_COOLDOWN_BAD (default 60s)
  - Applied for transient network errors
- QUARANTINE_FAILS (default 5)
  - If transient failures repeat and exceed this threshold, quarantine the account

Worker-side release logic (when a scraping worker finishes)
- release(success=True): short cooldown and decay fail_count (prevents immediate re-hammering)
- release(success=False): longer cooldown and increment fail_count
- For explicit rate-limit inside scraping logic:
  - call pool.cooldown(lease, seconds=ACCOUNT_MANAGER_COOLDOWN_RATE, reason="ratelimit") then release(success=False)

Global throttling (token bucket)
- scripts/account_pool_manager.py ensures a default bucket exists:
  - NAME: replace_more, CAPACITY: 5.0 tokens, REFILL: 2.0 tokens/sec (configurable)
- scraping/reddit/reddit_custom_scraper.py uses SqliteTokenBucketLimiter around heavy comment-tree expansions; this prevents spikes even if multiple accounts are free
- You can add more buckets (e.g., search, listing) if you want to shape overall QPS beyond Reddit’s quota

What we do NOT assume by default
- We do not hard-code “each account only 100 requests/min”. Reddit’s per-app and per-user quotas can differ and change over time; best practice is:
  - Use header-driven resets if available
  - Otherwise enforce safety caps:
    - Global heavy-op bucket (in place)
    - Per-account cooldown on 429
  - Monitor metrics and tune caps per environment

Recommended safety caps and tuning
- Start conservative:
  - Heavy-op bucket: capacity 5 tokens, refill 2 tokens/sec
  - Per-account concurrency: 1 (already enforced by leasing)
- Watch for 429s in metrics/logs:
  - If frequent 429 -> increase cooldown RATE, reduce concurrency or per-cycle items
- Observe latency and success rates:
  - If stable, you can increase refill rate for heavy bucket cautiously

State transition matrix (AccountPool + Manager)
- On successful health probe or scrape:
  - status := ready
  - cooldown_until := now (or min(existing, now))
  - fail_count := max(fail_count-1, 0)
- On 429 / “RATELIMIT”:
  - status := ready
  - cooldown_until := now + ACCOUNT_MANAGER_COOLDOWN_RATE (or header reset if available)
  - fail_count := fail_count + 1
  - reason := "rate-limit"
- On 401/403 or auth failure:
  - status := quarantine
  - reason := "auth"
- On transient network error:
  - status := ready
  - cooldown_until := now + ACCOUNT_MANAGER_COOLDOWN_BAD
  - fail_count := fail_count + 1
  - If fail_count >= QUARANTINE_FAILS => status := quarantine, reason := "repeated-failures"

Header-driven enhancement (optional future)
- We can instrument the asyncpraw requestor to capture response headers for each call and store:
  - last_seen_remaining, last_seen_reset on the account row
  - Then set cooldown_until precisely to now + reset if remaining ≈ 0
- This keeps cooldown aligned with Reddit’s exact reset window when headers are readable

Operational controls
- View status counts:
  sqlite3 storage/reddit/accounts.db "SELECT status, COUNT(*) FROM accounts GROUP BY status;"
- View cooling accounts:
  sqlite3 storage/reddit/accounts.db "SELECT account_id, username, cooldown_until FROM accounts WHERE status='ready' AND cooldown_until > strftime('%s','now');"
- View quarantined (and why):
  sqlite3 storage/reddit/accounts.db "SELECT account_id, username, last_error FROM accounts WHERE status='quarantine';"
- Prometheus (from account manager):
  curl -s http://localhost:9108/metrics | egrep 'reddit_pool_(ready|cooling|leased|quarantine)|reddit_pool_account_(check|cooldown|quarantine)_total'

Summary
- Logic is header-aware when feasible, but robust to missing headers by relying on 429/401/403/network signals + configurable cooldowns
- We do not assume a fixed 100 req/min per account; instead we:
  1) Cooldown on explicit rate-limit signals (429), optionally using reset headers if accessible
  2) Shape heavy operations with a global SQLite token bucket
  3) Use per-account cooldown and quarantine on repeated faults
- All of this is visible and tunable via env vars and Prometheus metrics, and the 24/7 account manager keeps the pool healthy even when no scrapes are running
