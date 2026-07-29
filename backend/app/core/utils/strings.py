"""Stateless string normalization helpers."""

import re


def normalize_whitespace(value: str) -> str:
    """Collapse consecutive whitespace and remove leading and trailing spaces."""
    return " ".join(value.split())


def to_slug(value: str) -> str:
    """Create a lowercase ASCII slug suitable for non-security identifiers."""
    normalized = normalize_whitespace(value).casefold()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", normalized)).strip("-")
