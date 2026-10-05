"""Which request paths are served from the platform store.

`_is_platform_path` decides the session every request gets. It matched with a
bare `startswith`, so `/api/v1/messaging` was read as `/api/v1/me` and the
whole messaging module was sent to the platform store, which holds none of its
tables: every route answered 503 on PostgreSQL (D-MSG-1, 2026-10-05). The unit
suite could not see it -- one SQLite schema holds every table -- and the
read-only sanity check skips platform paths, so it never walked them either.
"""

import inspect
import re

from app.core.database import dependencies
from app.core.database.dependencies import _is_platform_path


def test_a_platform_prefix_matches_a_whole_segment() -> None:
    """`/api/v1/me` is the platform's; `/api/v1/messaging` is a firm's."""
    assert _is_platform_path("/api/v1/me")
    assert _is_platform_path("/api/v1/me/firms")
    assert _is_platform_path("/health")
    assert not _is_platform_path("/api/v1/messaging")
    assert not _is_platform_path("/api/v1/messaging/settings")
    assert not _is_platform_path("/api/v1/firm-members")
    assert not _is_platform_path("/api/v1/customers")


def test_no_served_route_only_resembles_a_platform_prefix() -> None:
    """A route that starts like a platform prefix must be under it.

    Asked of the route table rather than of a list, so the next module whose
    name begins with `me`, `auth` or `firms` fails here on the day it is added.
    """
    from app.main import create_app

    prefixes = re.findall(
        r'"(/[^"]+)"', inspect.getsource(dependencies._is_platform_path)
    )
    assert "/api/v1/me" in prefixes, "the prefixes could not be read"
    lookalikes = sorted(
        path
        for path in create_app().openapi()["paths"]
        for prefix in prefixes
        if path.startswith(prefix)
        and not (path == prefix or path.startswith(f"{prefix}/"))
        and _is_platform_path(path)
    )
    assert lookalikes == [], f"sent to the platform store by resemblance: {lookalikes}"
