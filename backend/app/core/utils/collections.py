"""Stateless collection helpers."""

from collections.abc import Iterable, Iterator
from itertools import islice


def chunked[ItemT](items: Iterable[ItemT], size: int) -> Iterator[list[ItemT]]:
    """Yield bounded lists from an iterable."""
    if size < 1:
        raise ValueError("Chunk size must be at least one.")
    iterator = iter(items)
    while chunk := list(islice(iterator, size)):
        yield chunk
