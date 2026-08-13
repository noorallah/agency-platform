"""A paginated query sorted on a timestamp needs a tiebreaker.

``created_at`` and ``updated_at`` default to ``func.now()``, which in PostgreSQL
is ``transaction_timestamp()`` -- the instant the *transaction* began. Every row
one request writes therefore carries the same value, exactly. In the seeded
store 6,068 groups of ``audit_logs`` share an instant, up to thirteen rows at a
time.

A sort column that is not unique is not a total order, and ``OFFSET``/``LIMIT``
over a tie is free to hand the same row to two pages and never show another.
Adding the primary key as a final sort key costs nothing when the timestamps
differ and makes the order deterministic when they do not.

This reads the source rather than exercising the endpoints: the defect only
appears when rows tie, so a fixture that writes one row per request -- which is
most of them -- passes whether or not the tiebreaker is there.
"""

import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[2] / "app"

#: Timestamps every entity inherits, and neither of which is unique.
_SHARED_TIMESTAMPS = ("created_at", "updated_at")


def _order_by_blocks(source: str) -> list[tuple[int, str, str]]:
    """Return (line, sorted-columns, what-follows) for each order_by call."""
    blocks: list[tuple[int, str, str]] = []
    for match in re.finditer(r"\.order_by\(", source):
        index, depth, collected = match.end(), 1, []
        while index < len(source) and depth:
            char = source[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            collected.append(char)
            index += 1
        line = source[: match.start()].count("\n") + 1
        blocks.append((line, "".join(collected), source[index : index + 500]))
    return blocks


def test_every_paginated_timestamp_sort_ends_with_the_primary_key() -> None:
    """Find any page or cut ordered on a timestamp with no tiebreaker."""
    offenders: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for line, columns, tail in _order_by_blocks(source):
            if not any(stamp in columns for stamp in _SHARED_TIMESTAMPS):
                continue
            if ".offset(" not in tail and ".limit(" not in tail:
                continue
            # A tiebreaker may be in this call or appended by a later one:
            # SQLAlchemy's order_by adds to the clause rather than replacing it.
            if re.search(r"\.id[\.\s,)]", columns) or re.search(
                r"\.order_by\([^)]*\.id[\.\s,)]", tail
            ):
                continue
            offenders.append(
                f"{path.relative_to(_APP.parent).as_posix()}:{line} "
                f"-> {' '.join(columns.split())[:60]}"
            )
    assert not offenders, (
        "these paginate on a timestamp that every row in a request shares, so "
        "a page can repeat one row and hide another:\n  " + "\n  ".join(offenders)
    )
