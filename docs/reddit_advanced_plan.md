Title
RedditScraper: Scalable, multi-account, proxy-backed async Reddit scraping framework

Summary
Extend the existing RedditCustomScraper into a production-grade, high-throughput framework using up to 100 Reddit accounts and 500 residential proxies to parallelize data collection across posts, searches, user timelines, and realtime streams. Preserve current contracts (scrape, validate), add a new scrape_advanced driven by RedditScrapeOptions, and introduce an AccountPool for one-account-per-worker leasing with proxy binding, robust throttling/backoff, checkpointing, weighted job scheduling, and Prometheus metrics. Enable full comment-tree harvesting via replace_more(limit=None) with safety controls. Deliver tests, docs, deployment guidance, and monitoring.

Goals
- High-volume scraping across subreddits, keywords, and user timelines.
- Full comment-tree harvesting on-demand (throttled, depth/size guards).
- One account + one proxy per worker; quarantine/rotate on rate limits/errors.
- Backward compatibility: existing scrape() and validate() unchanged.
- New scrape_advanced() orchestration with checkpointing and optional streaming.
- Observability: metrics, health reporting, lightweight tracing (optional).
- Tests (unit/integration), docs, and deployment instructions.

Non-Goals (initial version)
- ML-based prioritization beyond weighted scheduling.
- Non-Reddit sources.
- Cross-cluster coordination beyond a single Redis/Postgres domain.

High-level architecture (ASCII)
                +-------------------------+
                |  ScrapingConfig / API   |
                +-----------+-------------+
                            |
                      JobQueue (json)
                            |
                 +----------v-----------+
                 |      JobManager      |
                 +----------+-----------+
                            |
            +---------------+-----------------+
            |                                 |
    +-------v-------+                 +-------v--------+
    | AccountPool    |                 |  ProxyPool     |
    | (100 accounts) |                 | (500 proxies)  |
    +-------+--------+                 +-------+--------+
            |                                  |
            +---------------+------------------+
                            |
                     WorkerPool (N workers)
          (each worker = AccountLease + Proxy assign)
                            |
                    ScraperEngine (asyncpraw)
   (scrape_advanced, listings, search, user_timeline, streams)
                            |
             Checkpointer -> Postgres/Sqllite (job progress)
                            |


Data flow
1) Config/API creates jobs with params (subreddit, keywords, date range, options).
2) Planner expands jobs to concrete targets (listings/search/timelines).
3) Worker acquires AccountLease from AccountPool (binds proxy), executes target via ScraperEngine.
4) Results validated/serialized into existing DataEntity/RedditContent, stored, deduped.
5) Checkpointer persists progress; AccountPool updates health and rate-limit state.
6) Metrics emitted for requests, items scraped, errors, backoffs.

Components and responsibilities
1) JobManager / JobQueue (scraping/reddit/job_queue.py)
- API: enqueue(job), dequeue(), ack(), nack(), reprioritize(weight).
- Weighted scheduling; small, retryable work-units:
  - subreddit_listing
  - submission_detail
  - submission_comments_chunk
  - user_timeline
  - search_target
  - stream_target
- Backend options: Redis Streams (default) or Kafka (pluggable).

2) AccountPool and ProxyPool (scraping/reddit/session_pool.py)
- AccountCredential: client_id, client_secret, username, password, refresh_token? (optional).
- ProxyConfig: host, port, username, password, provider_tag, metadata.
- AccountLease: (account_id, proxy_id, reddit_client, acquired_at, rate_limit_remaining, cooldown_until, status).
- AccountPool:
  - async acquire() -> AccountLease
  - async release(lease, success=True) -> None
  - health_report() -> Dict
  - Backoff/quarantine on 429/403; cooldown on low X-Ratelimit-Remaining.
- ProxyPool:
  - acquire()/release() with health metrics (latency, failures).
  - Rotation policy (per lease or every N requests).

3) RedditClientManager (in session_pool.py)
- build_client(account: AccountCredential, proxy: Optional[ProxyConfig]) -> asyncpraw.Reddit
- OAuth token management (FileTokenManager/SQLiteTokenManager optional).
- requestor kwargs to bind proxy.

4) Planner (scraping/reddit/planner.py)
- AdvancedScrapePlan plus target types:
  - SubmissionsTarget(listing_type, time_filter?, subreddit, limit)
  - SearchTarget(query, sort, time_filter?, subreddit, limit)
  - UserTimelineTarget(username, mode=submissions/comments, sort)
  - CommentsTarget(submission_id, harvest_mode, depth_limit)
- build_plan(subreddit, options, date_range) -> AdvancedScrapePlan
- expand_to_targets(plan) -> List[Target]
- Distribute pagination_target across surfaces; apply per_listing_limit.

5) ScraperEngine (scraping/reddit/reddit_custom_scraper.py)
- New method:
  - async scrape_advanced(scrape_config, options: RedditScrapeOptions, pool: Optional[AccountPool] = None) -> List[DataEntity]
- Helpers:
  - _iter_submissions(subreddit, listing_type, time_filter?, limit)
  - _iter_search(subreddit, query, sort, time_filter?, limit)
  - _iter_user_timeline(username, mode, sort, limit)
  - _harvest_all_comments(submission, depth_limit?, global_semaphore?)
  - _flatten_comment_forest(submission.comments, depth_limit?) -> Iterable[CommentData]
  - _merge_and_dedupe(entities) -> entities (uses Redis set/Bloom or in-memory fallback)
- Streaming support (if options.enable_streams):
  - async for s in subreddit.stream.submissions(skip_existing=True): ...
  - async for c in subreddit.stream.comments(skip_existing=True): ...
- Throttling envelope for replace_more(limit=None) via a global semaphore (e.g., max 5 concurrent expansions).
- Preserve existing scrape(), validate() and parsers; reuse RedditContent model and NSFW/media rules.

6) Checkpointer (scraping/reddit/checkpointer.py)
- API:
  - async save_progress(job_id: str, checkpoint: dict) -> None
  - async load_progress(job_id: str) -> Optional[dict]
- Backends: Redis hash (default) with optional Postgres persistence.
- Store last processed id/timestamp per target, and partial progress for large comment trees.

7) RateLimiter (scraping/reddit/rate_limiter.py)
- Optional global token bucket backed by Redis (keys per scope e.g. heavy_op:comments_expand).
- Integrates with AccountPool to cap concurrent heavy ops and shape cross-account usage.

8) Metrics & Monitoring (scraping/reddit/metrics.py)
- Prometheus client metrics:
  - Gauges: active_accounts, active_proxies, accounts_cooldown, global_replace_more_inflight
  - Counters: reddit_requests_total{endpoint}, items_scraped_total{type}, account_errors_total{kind}, proxy_failures_total{kind}
  - Histograms/Summaries: replace_more_time_seconds, submission_fetch_seconds
- Standard labels: subreddit, listing_type, harvest_mode, account_id (hashed).

9) StreamJobController (scraping/reddit/stream_controller.py)
- Orchestrates long-lived streams for configured subreddits and surfaces.
- API:
  - async run_forever(job_stream: AsyncIterator[ScrapeConfig]) -> None
  - async dispatch_job(job: ScrapeConfig) -> None

10) Integration with existing provider (scraping/provider.py)
- Keep ScraperId.REDDIT_CUSTOM -> RedditCustomScraper mapping.
- scrape() path unchanged; scrape_advanced() is opt-in and used by coordinator paths that understand RedditScrapeOptions.
- Coordinator receives optional AccountPool to pass down or uses single-client fallback.

New types and config (scraping/reddit/options.py)
- Enums:
  - ListingType: new, hot, top(time_filter), rising, controversial(time_filter), search
  - TimeFilter: hour, day, week, month, year, all
  - SortMode: relevance, hot, top, new, comments
  - CommentHarvestMode: post_only, top_level_only, all_comments
- RedditScrapeOptions (key fields):
  - include_submissions: bool
  - include_comments: bool
  - listing_types: List[ListingType]
  - time_filters: Optional[List[TimeFilter]]
  - search_queries: Optional[List[str]]
  - search_sort: SortMode
  - keyword_mode: "all" | "any"
  - user_timelines: Optional[List[str]]
  - pagination_target: Optional[int]
  - per_listing_limit: int = 100
  - harvest_mode: CommentHarvestMode = POST_ONLY
  - expand_comment_depth_limit: Optional[int]
  - concurrency: int = 1
  - enable_streams: bool = False
  - stream_surfaces: Optional[List[str]]
  - stream_timeout: Optional[int]
  - dedupe_on_uri: bool = True
- validate() checks invariants (e.g., SEARCH requires queries, limits positive).

File tree additions
scraping/reddit/
- reddit_custom_scraper.py   (extend with scrape_advanced, helpers, streaming)
- options.py                 (NEW)
- planner.py                 (NEW)
- session_pool.py            (NEW: AccountPool, RedditClientManager, AccountLease, ProxyPool)
- checkpointer.py            (NEW)
- rate_limiter.py            (NEW)
- job_queue.py               (NEW)
- stream_controller.py       (NEW)
- metrics.py                 (NEW)
- __init__.py                (export new types/classes)

Concrete APIs / method signatures
- AccountPool
  - class AccountPool:
      async def acquire(self) -> AccountLease: ...
      async def release(self, lease: AccountLease, success: bool = True) -> None: ...
      def health_report(self) -> Dict: ...
- RedditClientManager
  - def build_client(account: AccountCredential, proxy: Optional[ProxyConfig]) -> "asyncpraw.Reddit"
- RedditCustomScraper
  - async def scrape_advanced(self, scrape_config, options: RedditScrapeOptions, pool: Optional[AccountPool] = None) -> List["DataEntity"]
- Planner
  - def build_plan(subreddit: str, options: RedditScrapeOptions, date_range) -> "AdvancedScrapePlan"
  - def expand_to_targets(plan: "AdvancedScrapePlan") -> List["Target"]
- StreamJobController
  - class StreamJobController:
      async def run_forever(self, job_stream) -> None: ...
      async def dispatch_job(self, job) -> None: ...
- Checkpointer
  - class Checkpointer:
      async def save_progress(self, job_id: str, checkpoint: dict) -> None: ...
      async def load_progress(self, job_id: str) -> Optional[dict]: ...

Work units (task splitting)
- subreddit_listing — list posts by listing type/time_filter/query
- submission_detail — fetch single submission, metadata, optionally harvest comments
- submission_comments_chunk — process chunk of flattened comments to parallelize huge threads
- user_timeline — fetch redditor posts/comments
- search_target — search results for keyword across subreddit/all
- stream_target — long-lived stream of new submissions/comments
Workers pick one unit at a time. Units must be small and retryable.

Streaming integration
- subreddit.stream.submissions(skip_existing=True)
- subreddit.stream.comments(skip_existing=True)
- Stream jobs checkpoint only the last seen id; on restart use skip_existing to avoid duplication.

Rate limit and account management (defaults)
- Per-account concurrency: 1 worker.
- Per-account requests/min initial cap: 40; tune upward carefully.
- Active accounts fraction: 75% (keep 25% resting).
- Max concurrent heavy replace_more ops globally: 5.
- If X-Ratelimit-Remaining below threshold -> cooldown based on X-Ratelimit-Reset or exponential backoff.
- Quarantine accounts/proxies on repeated 429/403/connection failures.
- Proxy rotation: rotate proxy per lease or every N requests.

Checkpointing strategy
- Save per-job:
  - last_processed_submission_id
  - last_processed_comment_id or page offset
  - last_timestamp
- Submission detail jobs: save after finishing a batch or every N comments.
- Stream jobs: save last seen item frequently (every few seconds or after N items).

Deduplication and storage
- Dedupe keys: fullname (t3_/t1_) and URL.
- Maintain Redis set or Bloom filter for quick seen checks; fallback in-memory for single-process runs.
- Storage:
  - Raw JSON -> S3/MinIO for archive.
  - Metadata -> Postgres/ClickHouse for analytics (as per your pipeline).
- Preserve RedditContent serialization/obfuscation; NSFW/media rules unchanged.

Security and operations
- Load credentials from secrets (AWS Secrets Manager / Vault / env JSON). Do not commit creds.
- Rotate credentials periodically; monitor for bans; quarantine immediately on suspected bans.
- Comply with Reddit API ToS; only access content via API with valid credentials; avoid private content.

Testing strategy
- Unit tests:
  - options: defaults, enums, validate() invariants.
  - planner: build_plan and expand_to_targets across combinations (listing/time_filter/search/timelines).
  - comment flattening: _flatten_comment_forest depth limit; edge cases (deleted/removed).
  - merge & dedupe: URI/fullname dedupe across surfaces.
  - AccountPool: acquire/release, cooldown/backoff, quarantine.
- Integration (smoke):
  - scrape_advanced against a public subreddit with per_listing_limit small; verify DataEntity invariants.
  - streaming smoke with skip_existing=True for short duration.
- Mocks:
  - Mock asyncpraw Subreddit/Submission/CommentForest; simulate replace_more and errors.
- Performance checks:
  - Global semaphore correctness for replace_more; pagination_target capping; concurrency safety.

Deployment and scaling
- Dockerize workers and controllers.
- Kubernetes:
  - JobManager + StreamJobController (1..N replicas).
  - WorkerGroup scaled to desired parallelism; each worker acquires leases from central AccountPool (Redis-backed state).
  - Shared services: Redis (queue, state, dedupe), Postgres (checkpoints/meta), S3 (raw), Prometheus (metrics).
- Horizontal scaling: add worker nodes; ensure account/proxy capacity > workers.

Sample ScrapingConfig job (normalized)
```json
{
  "scraper_id": "Reddit.custom",
  "jobs": [
    {
      "id": "crawler-0-01rc2pj-esoqzdw5vaffu",
      "weight": 1.0,
      "params": {
        "keyword": "bittensor",
        "platform": "reddit",
        "label": null,
        "post_start_datetime": "2025-10-10T07:00:00Z",
        "post_end_datetime": "2025-11-10T07:59:59Z"
      }
    },
    {
      "id": "crawler-0-6qx7j0la5xhrdjgcpu8nf",
      "weight": 1.0,
      "params": {
        "keyword": "ploom, aura, ploom x, camel ploom, mevius ploom, winston ploom",
        "platform": "reddit",
        "label": null,
        "post_start_datetime": "2025-10-09T22:00:00Z",
        "post_end_datetime": "2025-11-09T22:59:59Z"
      }
    },
    {
      "id": "crawler-0-7lbwce6vujqyopqtf0v2a",
      "weight": 1.0,
      "params": {
        "keyword": "2025 mayoral race",
        "platform": "reddit",
        "label": "r/nyc",
        "post_start_datetime": "2025-10-06T23:00:00Z",
        "post_end_datetime": "2025-11-06T23:59:59Z"
      }
    }
  ]
}
```

Concrete APIs / method signatures (to implement)
- AccountPool
```python
class AccountPool:
    async def acquire(self) -> AccountLease: ...
    async def release(self, lease: AccountLease, success: bool = True) -> None: ...
    def health_report(self) -> Dict: ...
```
- RedditClientManager
```python
def build_client(account: AccountCredential, proxy: Optional[ProxyConfig]) -> asyncpraw.Reddit: ...
```
- RedditCustomScraper
```python
async def scrape_advanced(
    self,
    scrape_config: ScrapeConfig,
    options: RedditScrapeOptions,
    pool: Optional[AccountPool] = None
) -> List[DataEntity]: ...
```
- Planner
```python
def build_plan(subreddit: str, options: RedditScrapeOptions, date_range: DateRange) -> AdvancedScrapePlan
def expand_to_targets(plan: AdvancedScrapePlan) -> List[Target]
```
- StreamJobController
```python
class StreamJobController:
    async def run_forever(self, job_stream: AsyncIterator[ScrapeConfig]) -> None: ...
    async def dispatch_job(self, job: ScrapeConfig) -> None: ...
```
- Checkpointer
```python
class Checkpointer:
    async def save_progress(self, job_id: str, checkpoint: dict) -> None: ...
    async def load_progress(self, job_id: str) -> Optional[dict]: ...
```

Implementation roadmap (phased)
Phase 0: Foundations
- Add options.py (enums + RedditScrapeOptions + validate()).
- Add planner.py (AdvancedScrapePlan + expand_to_targets).
- Extend reddit_custom_scraper.py with scrape_advanced() stub and scaffolding.
- Minimal tests for options/planner.

Phase 1: Session pool and throttling
- Add session_pool.py (AccountCredential, ProxyConfig, AccountPool, RedditClientManager).
- Integrate optional pool into scrape_advanced(); fallback to single-client.
- Add global semaphore for replace_more; basic metrics.

Phase 2: Targets and harvesting
- Implement _iter_submissions, _iter_search, _iter_user_timeline.
- Implement _harvest_all_comments and _flatten_comment_forest with batching.
- Implement _merge_and_dedupe with in-memory and Redis mode.
- Tests for flattening and dedupe.

Phase 3: Reliability and checkpointing
- Add checkpointer.py; wire into scrape_advanced iterators.
- Add job_queue.py with weighted scheduling; define work-unit schemas.
- Expand tests for resume behavior and retry semantics.

Phase 4: Streaming and rate limiting
- Add stream_controller.py; implement submissions/comments streams.
- Add rate_limiter.py (Redis token bucket) and integrate heavy-op gating.
- Stream smoke tests.

Phase 5: Observability and docs
- Add metrics.py; instrument key paths.
- Update docs/reddit.md (config, examples, tradeoffs, rate-limit tuning, streaming).
- Provide deployment guide (Docker/K8s) and tuning checklist.

Backward compatibility and integration
- Preserve existing reddit_custom_scraper scrape() and validate(); do not change signatures or outputs.
- scrape_advanced() is opt-in and coexists without breaking provider wiring.
- Ensure NSFW/media filters and RedditContent serialization remain identical for overlapped surfaces.

Acceptance criteria
- New modules exist with documented APIs; lint/typing clean.
- scrape_advanced() can:
  - Enumerate configured listings/search/timelines and respect pagination_target.
  - Optionally harvest full comment trees with depth guard and global throttle.
  - Deduplicate entities; maintain existing data model invariants.
  - Run with and without AccountPool.
- Checkpointing supports resume across listings and long comment threads.
- Streaming mode works with skip_existing and checkpoint of last seen id.
- Metrics exported: request counts, items scraped, errors, replace_more durations.
- Unit tests for options, planner, flattening, dedupe, AccountPool; integration smoke passes.
- Docs updated with examples and operational notes.

Risks and mitigations
- Account bans or rate-limit spikes: aggressive cooldown/quarantine; keep 25% accounts resting; global limiter.
- replace_more hot spots on mega-threads: global semaphore and comment chunk work-units; pagination_target applied to submissions first.
- Proxy instability: health scoring and rotation; quarantine on repeated failures.
- API changes: isolate asyncpraw usage behind helper methods for easier updates.

Immediate next deliverables (skeletons)
- options.py: enums + RedditScrapeOptions + validate()
- planner.py: plan types + build_plan + expand_to_targets
- session_pool.py: AccountPool, ProxyPool, RedditClientManager
- reddit_custom_scraper.py: scrape_advanced() signature + stub helpers
- Tests: test_advanced_options.py, test_planner.py, test_harvest_comments.py (skeletons)
- Docs: draft section in docs/reddit.md describing advanced mode and account/proxy config

Tuning & rollout
- Start with conservative per-account caps and global replace_more cap.
- Monitor metrics (429s, errors, latencies); adjust active_accounts_fraction, caps, and cooldowns.
- Gradually enable ALL_COMMENTS on targeted subreddits before broad rollout.
