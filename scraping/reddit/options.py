from __future__ import annotations

from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator


class ListingType(str, Enum):
    NEW = "new"
    HOT = "hot"
    TOP = "top"
    RISING = "rising"
    CONTROVERSIAL = "controversial"
    SEARCH = "search"


class TimeFilter(str, Enum):
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    ALL = "all"


class SortMode(str, Enum):
    RELEVANCE = "relevance"
    HOT = "hot"
    TOP = "top"
    NEW = "new"
    COMMENTS = "comments"


class CommentHarvestMode(str, Enum):
    POST_ONLY = "post_only"
    TOP_LEVEL_ONLY = "top_level_only"
    ALL_COMMENTS = "all_comments"


class RedditScrapeOptions(BaseModel):
    include_submissions: bool = True
    include_comments: bool = True

    listing_types: List[ListingType] = Field(
        default_factory=lambda: [ListingType.NEW, ListingType.HOT, ListingType.TOP]
    )
    time_filters: Optional[List[TimeFilter]] = None

    search_queries: Optional[List[str]] = None
    search_sort: Optional[SortMode] = SortMode.NEW
    keyword_mode: Optional[Literal["all", "any"]] = "all"

    user_timelines: Optional[List[str]] = None

    pagination_target: Optional[int] = None
    per_listing_limit: int = 100

    harvest_mode: CommentHarvestMode = CommentHarvestMode.POST_ONLY
    expand_comment_depth_limit: Optional[int] = None

    concurrency: int = 1
    enable_streams: bool = False
    stream_surfaces: Optional[List[str]] = None
    stream_timeout: Optional[int] = None

    dedupe_on_uri: bool = True

    @validator("per_listing_limit")
    def _positive_limit(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("per_listing_limit must be positive")
        return v

    @validator("pagination_target")
    def _non_negative_target(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("pagination_target must be positive if provided")
        return v

    @validator("listing_types")
    def _non_empty_listing_types(cls, v: List[ListingType]) -> List[ListingType]:
        if not v:
            raise ValueError("listing_types cannot be empty")
        return v

    @validator("search_queries", always=True)
    def _search_requires_queries(cls, v, values):
        listing_types: List[ListingType] = values.get("listing_types") or []
        if ListingType.SEARCH in listing_types and (not v or len(v) == 0):
            raise ValueError("SEARCH listing requires non-empty search_queries")
        return v
