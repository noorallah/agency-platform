"""Ask about many ids without passing them all in one statement.

A query with ``column.in_(ids)`` sends one bind parameter per id, and the
PostgreSQL driver refuses a statement with more than 65,535 of them. Two years
of a mid-size distributor is about 100,000 invoices, so a report asking "what
has been paid against each of these" over every open invoice fails outright
rather than running slowly (backlog 56 C, ``docs/PERFORMANCE_AT_VOLUME.md``).

``over_chunks`` splits the named id argument, calls the function once per
chunk, and merges the answers. It fits the functions whose answer is keyed by
those ids -- a dict per id, or a set of ids -- because then a chunk's answer
never overlaps another's and merging is exact.

``whole_past_a_chunk`` is the other answer, for a function that can also be
asked about *everything* -- its id argument accepts None. Past one chunk it
asks once for everything and keeps the ids it was given: one grouped read over
a firm's allocations is far cheaper than twenty statements naming 5,000 ids
each, which spent most of their time having the ids bound and parsed (backlog
56 C, step 4).
"""

from collections.abc import Callable, Iterator, Sequence
from functools import wraps
from inspect import signature
from typing import Any, TypeVar
from uuid import UUID

#: Well under the driver's 65,535, leaving room for the other parameters a
#: statement carries, and small enough that one chunk plans quickly.
CHUNK_SIZE = 5000

ResultT = TypeVar("ResultT", dict[Any, Any], set[Any])


def chunks(ids: Sequence[UUID], size: int | None = None) -> Iterator[list[UUID]]:
    """Yield ``ids`` in lists of at most ``size`` (default :data:`CHUNK_SIZE`)."""
    step = size or CHUNK_SIZE
    unique = list(dict.fromkeys(ids))
    for start in range(0, len(unique), step):
        yield unique[start : start + step]


def over_chunks(
    argument: str,
) -> Callable[[Callable[..., ResultT]], Callable[..., ResultT]]:
    """Run the decorated function per chunk of the keyword ``argument``.

    The argument may be passed by position or by keyword. A call with no
    more ids than one chunk runs exactly as before; a larger one is split and
    its answers merged -- dicts by update, sets by union.
    """

    def decorate(function: Callable[..., ResultT]) -> Callable[..., ResultT]:
        """Wrap ``function``."""
        shape = signature(function)

        @wraps(function)
        def run(*args: object, **kwargs: object) -> ResultT:
            """Call once, or once per chunk and merge."""
            bound = shape.bind(*args, **kwargs)
            raw = bound.arguments.get(argument)
            if raw is None:
                return function(*args, **kwargs)
            # Read once, here: a generator must reach every chunk.
            ids: list[UUID] = list(raw)
            bound.arguments[argument] = ids
            if len(ids) <= CHUNK_SIZE:
                return function(*bound.args, **bound.kwargs)
            answers: list[ResultT] = []
            for chunk in chunks(ids):
                bound.arguments[argument] = chunk
                answers.append(function(*bound.args, **bound.kwargs))
            return _merged(answers)

        return run

    return decorate


def whole_past_a_chunk[KeyT, ValueT](
    argument: str,
) -> Callable[[Callable[..., dict[KeyT, ValueT]]], Callable[..., dict[KeyT, ValueT]]]:
    """Answer more than a chunk of ``argument`` by asking about everything.

    The decorated function must accept None for ``argument`` and mean "every
    id", and its answer must be a dict keyed by those ids. A call naming no
    more than one chunk runs exactly as before.
    """

    def decorate(
        function: Callable[..., dict[KeyT, ValueT]],
    ) -> Callable[..., dict[KeyT, ValueT]]:
        """Wrap ``function``."""
        shape = signature(function)

        @wraps(function)
        def run(*args: object, **kwargs: object) -> dict[KeyT, ValueT]:
            """Call as given, or once for everything and keep what was asked."""
            bound = shape.bind(*args, **kwargs)
            ids = bound.arguments.get(argument)
            if ids is None or len(ids) <= CHUNK_SIZE:
                return function(*args, **kwargs)
            wanted = set(ids)
            bound.arguments[argument] = None
            everything = function(*bound.args, **bound.kwargs)
            return {key: value for key, value in everything.items() if key in wanted}

        return run

    return decorate


def _merged[MergedT: (dict[Any, Any], set[Any])](answers: list[MergedT]) -> MergedT:
    """Merge per-chunk answers: dicts by update, sets by union."""
    first = answers[0]
    for answer in answers[1:]:
        if isinstance(first, dict) and isinstance(answer, dict):
            first.update(answer)
        elif isinstance(first, set) and isinstance(answer, set):
            first |= answer
    return first
