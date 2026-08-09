"""Schemas for enterprise global search responses."""

from typing import Literal

from pydantic import BaseModel, Field

SearchCategory = Literal[
    "all",
    "masters",
    "inventory",
    "tax",
    "organization",
]


class SearchResultItem(BaseModel):
    """One normalized search hit used by desktop quick search."""

    id: str
    entity_type: str
    module: str
    tab: str | None = None
    title: str
    subtitle: str | None = None
    status: str | None = None
    icon: str
    badges: list[str] = Field(default_factory=list)
    navigation_path: str | None = None
    matched_fields: list[str] = Field(default_factory=list)


class SearchResultPage(BaseModel):
    """Paginated global search result payload."""

    query: str
    category: SearchCategory
    page: int
    page_size: int
    total: int
    results: list[SearchResultItem]

