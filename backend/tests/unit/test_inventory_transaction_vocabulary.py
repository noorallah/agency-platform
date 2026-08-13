"""Keep the declared movement vocabulary equal to the written one.

``InventoryTransactionType`` declared fourteen members. Six were written, and
three of the written ones were missing: the service recorded RESERVE, UNRESERVE
and DISPATCH while the enum offered RESERVATION and RESERVATION_RELEASE, along
with GOODS_ISSUE, TRANSFER_IN, TRANSFER_OUT, PHYSICAL_COUNT, DAMAGE, EXPIRY,
QUARANTINE and CORRECTION -- none of which anything emitted.

The transaction filter was typed by that enum, so on a firm that had traded:
filtering by RESERVE was rejected as invalid, and filtering by RESERVATION was
accepted and matched nothing. Three of the four movement types in a live store
could not be filtered for at all.

These tests read the service's source rather than its behaviour on purpose. The
drift is between a literal and an enum member, which no amount of exercising
one code path reveals -- only comparing the two lists does.
"""

import re
from pathlib import Path

from app.inventory.schemas import REVERSAL_SUFFIX, InventoryTransactionType

_SERVICE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "inventory"
    / "services"
    / "inventory_service.py"
)


def _written_types() -> set[str]:
    """Return every movement type the service assigns as a bare literal."""
    source = _SERVICE.read_text(encoding="utf-8")
    return set(re.findall(r'transaction_type="([A-Z_]+)"', source))


def test_the_service_writes_no_type_the_enum_does_not_declare() -> None:
    """A literal outside the enum is a type no caller can filter for."""
    undeclared = sorted(
        _written_types() - {member.value for member in InventoryTransactionType}
    )
    assert not undeclared, (
        f"the service writes {undeclared}, which the enum does not declare. "
        "Add the member, or write the member's value instead of a literal."
    )


def test_the_enum_declares_nothing_the_system_cannot_produce() -> None:
    """A member nothing writes advertises a movement that never happens.

    Transfers, physical counts and damage write-offs are not built. Declaring
    them offered a filter that could only ever return an empty page.
    """
    source = _SERVICE.read_text(encoding="utf-8")
    unwritten = sorted(
        member.value
        for member in InventoryTransactionType
        if f"InventoryTransactionType.{member.name}" not in source
        and f'transaction_type="{member.value}"' not in source
    )
    assert not unwritten, (
        f"the enum declares {unwritten}, which nothing writes. Build the "
        "movement or document it as absent instead of advertising it."
    )


def test_a_reversal_is_filterable_even_though_no_enum_can_name_it() -> None:
    """The stored vocabulary is open-ended, so the filter takes a string.

    ``reverse_transaction`` writes "<TYPE>_REVERSAL", and reversing a reversal
    is legal -- the service refuses only to reverse the same row twice -- so
    the set of stored values has no upper bound and a closed filter can never
    cover it.
    """
    from app.inventory.schemas import InventoryTransactionListFilters

    for value in (
        InventoryTransactionType.DISPATCH.value,
        f"{InventoryTransactionType.DISPATCH.value}{REVERSAL_SUFFIX}",
        f"{InventoryTransactionType.DISPATCH.value}{REVERSAL_SUFFIX}"
        f"{REVERSAL_SUFFIX}",
    ):
        filters = InventoryTransactionListFilters.model_validate(
            {"transaction_type": value}
        )
        assert filters.transaction_type == value
