# Implementation Plan

[Overview]
Scale Reddit scraping throughput and coverage by extending RedditCustomScraper to support richer asyncpraw listings/search, full comment-tree expansion, and controlled concurrency via an account+proxy pool, while maintaining current DataEntity schema, validation rules, and NSFW/media policies.

This implementation introduces an options layer tailored to Reddit scraping needs, allowing schedulers to precisely configure which surfaces to hit (submissions and comments, listings like new/top/hot/rising/controversial, subreddit search with time filters and sorts, user timelines) and whether to harvest entire comment trees for each post. A lightweight account/worker pool abstracts 100+ Reddit accounts and 500 residential proxies for safe parallelization (one account per worker). The plan preserves backward compatibility: existing scrape() behavior remains valid, while new advanced behavior becomes opt-in via additional methods and new types.

The approach adds three main components: (1) explicit RedditScrapeOptions to describe desired volume/coverage behavior; (2) an AccountPool and RedditClientManager to lease pre-configured asyncpraw clients bound to an account+proxy; (3) an AdvancedScrapePlanner to combine multiple listings, pagination targets, and optional expansion of complete comment trees using asyncpraw’s CommentForest.replace_more(limit=None). These parts integrate into RedditCustomScraper via a new scrape_advanced() method and helpers, leaving validate() unchanged.

[Types]  
Extend the type system with Reddit-specific options and internal planning structures.

New types (pydantic StrictBaseModel unless noted):
- scraping/reddit/options.py
  - class ListingType(str, Enum):
    - NEW, HOT, TOP, RISING, CONTROVERSIAL, SEARCH
  - class TimeFilter(str, Enum):
    - HOUR, DAY, WEEK, MONTH, YEAR, ALL
  - class SortMode(str, Enum):
    - RELEVANCE, HOT, TOP, NEW, COMMENTS
  - class CommentHarvestMode(str, Enum):
    - POST_ONLY: only the submission (no extra comments)
    - TOP_LEVEL_ONLY: fetch only top-level comments
    - ALL_COMMENTS: fetch full tree (replace_more(limit=None) and flatten)
  - class RedditScrapeOptions:
    - include_submissions: bool = True
    - include_comments: bool = True
    - listing_types: List[ListingType] = [ListingType.NEW, ListingType.HOT, ListingType.TOP]
    - time_filters: Optional[List[TimeFilter]] = None
      - Applies to TOP/CONTROVERSIAL/SEARCH when relevant
    - search_queries: Optional[List[str]] = None
      - If present and listing_types includes SEARCH, build sub.search for each query
    - search_sort: Optional[SortMode] = SortMode.NEW
    - keyword_mode: Optional[str] = "all" | "any" (default "all") for query building convenience
    - user_timelines: Optional[List[str]] = None
      - redditor submissions/comments scrape
    - pagination_target: Optional[int] = None
      - Total number of items to aim for across combined listings (submissions+comments+search)
    - per_listing_limit: int = 100
      - Upper bound per listing generator
    - harvest_mode: CommentHarvestMode = POST_ONLY
    - expand_comment_depth_limit: Optional[int] = None
      - Optional safety cutoff for extremely large trees in ALL_COMMENTS mode
    - concurrency: int = 1
      - Upper bound of concurrent listing iterators within a single worker
    - dedupe_on_uri: bool = True
      - Deduplicate by URL across merged listings
- scraping/reddit/session_pool.py
  - class AccountCredential(StrictBaseModel):
    - client_id: str
    - client_secret: str
    - username: str
    - password: str
  - class ProxyConfig(StrictBaseModel):
    - http: Optional[str]
    - https: Optional[str]
  - class AccountLease(StrictBaseModel):
    - account: AccountCredential
    - proxy: Optional[ProxyConfig]
    - reddit: asyncpraw.Reddit (runtime object, not serialized)
    - release(): None
  - class AccountPool:
    - acquire() -> AccountLease
    - release(lease: AccountLease) -> None
    - health reporting: track failures/rate-limits and quarantine unhealthy accounts
  - class RedditClientManager:
    - build_client(account: AccountCredential, proxy: Optional[ProxyConfig]) -> asyncpraw.Reddit
      - Pass requestor_kwargs={"proxies": {"http": proxy.http, "https": proxy.https}} when provided
- scraping/reddit/planner.py
  - class AdvancedScrapePlan(StrictBaseModel):
    - subreddit: str ("all" or specific)
    - options: RedditScrapeOptions
    - date_range: DateRange (from ScrapeConfig)
    - computed_targets: internal expansion of requested listings (e.g., list of query surfaces)
  - Plan entries (internal dataclasses):
    - SubmissionsTarget(listing: ListingType, time_filter: Optional[TimeFilter], sort: Optional[SortMode])
    - CommentsTarget(limit: int)
    - SearchTarget(query: str, sort: SortMode, time_filter: Optional[TimeFilter])
    - UserTimelineTarget(username: str, surface: "submissions"|"comments", listing: ListingType, time_filter: Optional[TimeFilter])

[Files]
Add new modules and modify the custom scraper; keep existing contracts intact.

New files:
- scraping/reddit/options.py
  - Holds RedditScrapeOptions and enums for listing/time_filter/sort/comment harvest mode.
- scraping/reddit/session_pool.py
  - Implements AccountPool, AccountLease, RedditClientManager for N-accounts + proxy integration.
- scraping/reddit/planner.py
  - Builds AdvancedScrapePlan surfaces from options and date_range; merges pagination targets; dedupe strategy.

Existing files to modify:
- scraping/reddit/reddit_custom_scraper.py
  - Add method: async def scrape_advanced(self, scrape_config: ScrapeConfig, options: RedditScrapeOptions, pool: Optional[AccountPool] = None) -> List[DataEntity]
    - Uses AccountPool (if provided) to lease one client for the duration; else creates a single client from environment, preserving current behavior.
    - Orchestrates multiple listings (submissions, comments, search, user timelines) according to options and date_range.
    - Supports pagination_target across iterable surfaces (accumulate until target reached).
    - Implements full comment harvest path based on harvest_mode using replace_more(limit=None) and flattening.
    - Applies existing NSFW+media rejection and RedditContent parsing.
  - Add helper methods:
    - _iter_submissions(subreddit, listing: ListingType, time_filter, per_listing_limit)
    - _iter_comments(subreddit, per_listing_limit)
    - _iter_search(subreddit, query, sort, time_filter, per_listing_limit)
    - _iter_user_timeline(redditor, surface, listing, time_filter, per_listing_limit)
    - _harvest_all_comments(submission)
    - _flatten_comment_forest(comment_forest, depth_limit)
    - _merge_and_dedupe(contents, dedupe_on_uri)
  - Keep existing scrape() and on_demand_scrape() unchanged for backward compatibility.
- docs/reddit.md
  - Document advanced options, account pool expectations, and tradeoffs of ALL_COMMENTS harvesting.

Files to delete or move:
- None.

Configuration updates:
- Allow opt-in configuration for AccountPool via environment or injected config:
  - e.g., REDDIT_ACCOUNTS_JSON (list of account creds) and PROXY_POOL_JSON (list of proxies), or integrate via constructor injection in coordinator layer.
- No changes to requirements.txt (asyncpraw already present).

[Functions]
Add new functions to orchestrate multi-surface scraping and comment-tree harvesting.

New functions (signatures, purpose):
- scraping/reddit/reddit_custom_scraper.py
  - async def scrape_advanced(self, scrape_config: ScrapeConfig, options: RedditScrapeOptions, pool: Optional[AccountPool] = None) -> List[DataEntity]
    - Orchestrates multiple listing iterators per options and merges results to DataEntity list.
  - async def _harvest_all_comments(self, submission: asyncpraw.models.Submission, depth_limit: Optional[int]) -> List[RedditContent]
    - Calls await submission.comments.replace_more(limit=None), then flattens to List[RedditContent] (comments only).
  - def _flatten_comment_forest(self, forest, depth_limit: Optional[int]) -> List[asyncpraw.models.Comment]
    - Depth-first flattening with optional depth limit.
  - async def _iter_submissions(self, subreddit, listing, time_filter, per_listing_limit): -> AsyncIterator[asyncpraw.models.Submission]
  - async def _iter_comments(self, subreddit, per_listing_limit): -> AsyncIterator[asyncpraw.models.Comment]
  - async def _iter_search(self, subreddit, query, sort, time_filter, per_listing_limit): -> AsyncIterator[Union[Submission, Comment]]
  - async def _iter_user_timeline(self, redditor, surface, listing, time_filter, per_listing_limit): -> AsyncIterator[Union[Submission, Comment]]
  - def _merge_and_dedupe(self, contents: List[RedditContent], dedupe_on_uri: bool) -> List[RedditContent]
- scraping/reddit/planner.py
  - def build_plan(subreddit: str, options: RedditScrapeOptions, date_range: DateRange) -> AdvancedScrapePlan
  - def expand_to_targets(plan: AdvancedScrapePlan) -> List[Union[SubmissionsTarget, CommentsTarget, SearchTarget, UserTimelineTarget]]

Modified functions:
- None of the existing public methods’ signatures change; scrape() and validate() remain as-is. Internal helpers in reddit_custom_scraper.py will be extended or added.

Removed functions:
- None.

[Classes]
Introduce account/pool management and a planner; minimally adjust RedditCustomScraper.

New classes:
- scraping/reddit/session_pool.py
  - AccountPool: manages queue of AccountCredential+ProxyConfig pairs; provides acquire/release, health tracking (e.g., backoff when rate-limited).
  - RedditClientManager: factory for asyncpraw.Reddit instances with per-lease proxy configuration.
- scraping/reddit/planner.py
  - AdvancedScrapePlan: holds expanded plan; utility to generate surface targets from options.
- scraping/reddit/options.py
  - ListingType, TimeFilter, SortMode, CommentHarvestMode enums
  - RedditScrapeOptions

Modified classes:
- RedditCustomScraper (scraping/reddit/reddit_custom_scraper.py)
  - Add scrape_advanced() and helper methods listed above.
  - Ensure NSFW+media filtering remains identical.
  - Ensure RedditContent parsing remains consistent; maintain obfuscation and DataEntity creation.

Removed classes:
- None.

[Dependencies]
No dependency additions are required; asyncpraw is already used. Optionally consider adding backoff or tenacity for rate-limit handling inside AccountPool health logic; this can be deferred.

[Testing]
Add tests covering planning, merging, and harvesting behaviors.

New tests:
- tests/scraping/reddit/test_advanced_options.py
  - Validate RedditScrapeOptions defaults and enum parsing.
  - Test build_plan/expand_to_targets correctness given various options.
- tests/scraping/reddit/test_harvest_comments.py
  - Mock asyncpraw Submission with nested comments; verify ALL_COMMENTS mode flattens to expected count and respects depth limit.
- tests/scraping/reddit/test_merge_and_dedupe.py
  - Ensure content deduping by URL works across mixed listings (new/top/hot/search).
- tests/integration/test_custom_advanced_scrape.py (optional/integration)
  - Smoke test with low limits against a known subreddit; verify no exceptions and DataEntity fields validity.

Existing tests:
- No changes required to current tests; backward compatibility is preserved for existing scrape()/validate().

[Implementation Order]
Implement types and planner first, then session pool, then scraper methods, then tests and docs.

1) Add scraping/reddit/options.py with enums and RedditScrapeOptions.
2) Add scraping/reddit/planner.py with AdvancedScrapePlan and target expansion utilities.
3) Add scraping/reddit/session_pool.py with AccountCredential, ProxyConfig, AccountPool, RedditClientManager.
4) Extend scraping/reddit/reddit_custom_scraper.py:
   - Add scrape_advanced() and helpers (_iter_* functions, _harvest_all_comments, _merge_and_dedupe).
   - Preserve existing scrape() and on_demand_scrape() unchanged.
5) Update docs/reddit.md with advanced usage examples and notes on comment tree harvesting costs.
6) Add unit tests under tests/scraping/reddit for options, planning, merging, and harvesting.
7) (Optional) Add integration smoke test with small limits.
8) Validate manual run paths and ensure NSFW+media policy still enforced uniformly.
