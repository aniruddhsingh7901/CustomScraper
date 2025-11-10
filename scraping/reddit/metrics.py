from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Gauges
active_accounts = Gauge(
    "reddit_active_accounts",
    "Number of active (leased) accounts",
)

accounts_cooldown = Gauge(
    "reddit_accounts_cooldown",
    "Number of accounts in cooldown",
)

global_replace_more_inflight = Gauge(
    "reddit_replace_more_inflight",
    "Number of concurrent replace_more expansions in flight",
)

# Counters
requests_total = Counter(
    "reddit_requests_total",
    "Total Reddit API requests (best-effort count)",
    labelnames=("endpoint",),
)

items_scraped_total = Counter(
    "reddit_items_scraped_total",
    "Total items scraped",
    labelnames=("type", "subreddit"),
)

account_errors_total = Counter(
    "reddit_account_errors_total",
    "Account-level errors (e.g., 403/429)",
    labelnames=("kind",),
)

proxy_failures_total = Counter(
    "reddit_proxy_failures_total",
    "Proxy failures (network errors, etc.)",
    labelnames=("kind",),
)

# Histograms
replace_more_time_seconds = Histogram(
    "reddit_replace_more_time_seconds",
    "Time spent in replace_more(limit=None)",
    buckets=(0.1, 0.3, 0.7, 1.5, 3.0, 6.0, 12.0, 24.0, 48.0),
)


def inc_request(endpoint: str) -> None:
    try:
        requests_total.labels(endpoint=endpoint).inc()
    except Exception:
        pass


def inc_items(item_type: str, subreddit: str, n: int = 1) -> None:
    try:
        items_scraped_total.labels(type=item_type, subreddit=subreddit).inc(n)
    except Exception:
        pass


class ReplaceMoreTimer:
    def __enter__(self):
        self._timer = replace_more_time_seconds.time()
        global_replace_more_inflight.inc()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if hasattr(self, "_timer"):
                self._timer.__exit__(exc_type, exc, tb)
        finally:
            global_replace_more_inflight.dec()


def measure_replace_more():
    return ReplaceMoreTimer()
