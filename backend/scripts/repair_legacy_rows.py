"""Repair legacy rows across every firm store, once.

The owner's decision of 2026-09-24 (decided by Claude, industry standard):

* a soft-deleted customer still carrying a balance is restored;
* a soft-deleted product still holding stock is restored;
* in the shared store, a customer, vendor or product reference to another
  firm's segment, category or type is set to NULL (D-MST-3);
* goodwill points granted before #477 and never accrued are trued up with
  one journal per firm, Dr 5700 / Cr 2600, reference
  ``LOY-GOODWILL-TRUEUP-<firm code>`` (D-SELL-19).

It is idempotent, and ``--dry-run`` is the default: it reports per store and
per firm what it would do, including a store it could not read, and changes
nothing.

    uv run python scripts/repair_legacy_rows.py              # dry run
    uv run python scripts/repair_legacy_rows.py --yes

**The work is in ``app/common/legacy_repair.py``**, which the unit tests call
directly.
"""

import argparse
import sys

from app.common.legacy_repair import repair_every_store


def main() -> int:
    """Report, or apply, every legacy repair across every store."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be repaired and change nothing (the default).",
    )
    group.add_argument("--yes", action="store_true", help="Apply the repairs.")
    parser.add_argument(
        "--actor-email",
        default=None,
        help=(
            "Whose name the audit rows and the journal carry. Defaults to the "
            "longest-standing platform administrator."
        ),
    )
    args = parser.parse_args()
    return repair_every_store(dry_run=not args.yes, actor_email=args.actor_email)


if __name__ == "__main__":
    sys.exit(main())
