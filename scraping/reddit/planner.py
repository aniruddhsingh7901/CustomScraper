from __future__ import annotations

from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field

from common.date_range import DateRange
from .options import (
    RedditScrapeOptions,
    ListingType,
    TimeFilter,
    SortMode,
    CommentHarvestMode,
)


# Target types for execution ----------------------------------------------------


class SubmissionsTarget(BaseModel):
    subreddit: str
    listing: ListingType
    time_filter: Optional[TimeFilter] = None
    sort: Optional[SortMode] = None
    limit: int = 100


class SearchTarget(BaseModel):
    subreddit: str
    query: str
    sort: SortMode = SortMode.NEW
    time_filter: Optional[TimeFilter] = None
    limit: int = 100


class UserTimelineTarget(BaseModel):
    username: str
    surface: Literal["submissions", "comments"]
    sort: SortMode = SortMode.NEW
    limit: int = 100


class CommentsTarget(BaseModel):
    submission_id: str
    harvest_mode: CommentHarvestMode = CommentHarvestMode.POST_ONLY
    depth_limit: Optional[int] = None


Target = Union[SubmissionsTarget, SearchTarget, UserTimelineTarget, CommentsTarget]


class AdvancedScrapePlan(BaseModel):
    subreddit: str
    options: RedditScrapeOptions
    date_range: DateRange
    computed_targets: List[Target] = Field(default_factory=list)


# Planner API ------------------------------------------------------------------


def build_plan(subreddit: str, options: RedditScrapeOptions, date_range: DateRange) -> AdvancedScrapePlan:
    """
    Build a plan from high-level options. This does not enumerate submissions,
    it just creates abstract targets that the engine will execute.
    """
    plan = AdvancedScrapePlan(
        subreddit=subreddit,
        options=options,
        date_range=date_range,
        computed_targets=[],
    )

    # Subreddit listings (except SEARCH)
    for listing in options.listing_types:
        if listing == ListingType.SEARCH:
            continue

        # Only TOP and CONTROVERSIAL support time filters in Reddit listing
        if listing in (ListingType.TOP, ListingType.CONTROVERSIAL):
            tfs = options.time_filters or [None]
            for tf in tfs:
                plan.computed_targets.append(
                    SubmissionsTarget(
                        subreddit=subreddit,
                        listing=listing,
                        time_filter=tf,
                        sort=None,
                        limit=options.per_listing_limit,
                    )
                )
        else:
            plan.computed_targets.append(
                SubmissionsTarget(
                    subreddit=subreddit,
                    listing=listing,
                    time_filter=None,
                    sort=None,
                    limit=options.per_listing_limit,
                )
            )

    # Search targets
    if ListingType.SEARCH in options.listing_types and options.search_queries:
        tfs = options.time_filters or [None]
        for q in options.search_queries:
            for tf in tfs:
                plan.computed_targets.append(
                    SearchTarget(
                        subreddit=subreddit,
                        query=q,
                        sort=options.search_sort or SortMode.NEW,
                        time_filter=tf,
                        limit=options.per_listing_limit,
                    )
                )

    # User timelines
    if options.user_timelines:
        for username in options.user_timelines:
            # submissions surface
            plan.computed_targets.append(
                UserTimelineTarget(
                    username=username,
                    surface="submissions",
                    sort=SortMode.NEW,
                    limit=options.per_listing_limit,
                )
            )
            # comments surface
            plan.computed_targets.append(
                UserTimelineTarget(
                    username=username,
                    surface="comments",
                    sort=SortMode.NEW,
                    limit=options.per_listing_limit,
                )
            )

    return plan


def expand_to_targets(plan: AdvancedScrapePlan) -> List[Target]:
    """
    Return the list of abstract targets to be executed by the scraper.
    """
    return list(plan.computed_targets)
