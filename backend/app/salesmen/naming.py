"""How an entry made for a user is named, shared by the migration and the rename.

The migration that builds the list (`20261014_0380`) names each entry from the
user's ``full_name`` where it can read ``platform.users``, and with a
placeholder where it cannot; ``upgrade_every_store`` later renames the
placeholders from the platform store. Both must spell the placeholder, and
settle a clash of names, the same way, so the rules live here once.
"""

from collections.abc import Collection
from uuid import UUID

#: The longest name the list holds (`salesmen.name`).
NAME_LENGTH = 120


def placeholder_name(user_id: UUID) -> str:
    """Name an entry whose user's name could not be read."""
    return f"Salesman {str(user_id)[:8]}"


def free_name(wanted: str, user_id: UUID, taken: Collection[str]) -> str | None:
    """Return ``wanted``, or it with the id's first eight characters after it.

    ``taken`` holds the firm's live names in lower case. Returns None when
    both are taken; the caller leaves the entry as it is.
    """
    suffix = str(user_id)[:8]
    for candidate in (
        wanted[:NAME_LENGTH],
        f"{wanted[: NAME_LENGTH - len(suffix) - 1]} {suffix}",
    ):
        if candidate.lower() not in taken:
            return candidate
    return None
