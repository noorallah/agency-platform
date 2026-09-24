"""What a master's display name becomes when the master is edited.

Vendors, branches and warehouses each keep a ``display_name`` beside their
``name``, and each update recomputed it from the name whenever one was sent --
so a trading name typed once was lost to the next edit of anything else
(D-MST-11). This is the one rule all three now follow.
"""


def display_name_after_edit(
    *,
    current: str,
    previous_name: str,
    name: str,
    sent: str | None,
    was_sent: bool,
) -> str:
    """Return the display name an edit leaves.

    Args:
        current: The display name the row holds before the edit.
        previous_name: The row's name before the edit.
        name: The row's name after the edit.
        sent: The display name the request carried, if any.
        was_sent: Whether the request named ``display_name`` at all.

    Returns:
        What was sent, or the name when it was sent blank. When it was not
        sent, a display name that merely followed the old name follows the new
        one, and a custom one is kept.

    """
    if was_sent:
        return sent or name
    return name if current == previous_name else current
