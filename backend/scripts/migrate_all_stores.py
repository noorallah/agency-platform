"""Upgrade every database and schema the firm registry knows about.

``alembic/env.py`` migrates exactly one schema per run, chosen by
``AGENCY_DATABASE_SCHEMA``. So a bare ``alembic upgrade head`` advances only the
platform schema and silently leaves every firm store behind, and the drift is
invisible until a query hits a missing column -- which is how every product read
in three firm schemas broke on 2026-08-09.

    uv run python scripts/migrate_all_stores.py --dry-run
    uv run python scripts/migrate_all_stores.py --yes

``--dry-run`` reports each target with the revision it is currently at and
changes nothing. Run it first: it is also the quickest way to see whether any
store has drifted.

**The work is in ``app/core/tenancy/migrations.py``**, not here. It moved on
2026-09-17 because a built copy of this product has no interpreter to hand a
script to, and firm provisioning needs the same "upgrade one store" call --
having it in one place is what stops the two drifting. This file stays as the
documented developer command, and is the same code the shipped
``agency-server migrate-all`` runs.
"""

import argparse

from app.core.tenancy.migrations import upgrade_every_store


def main() -> int:
    """Report or apply `upgrade head` against every store in the registry."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="List every target and its current revision, and change nothing.",
    )
    group.add_argument("--yes", action="store_true", help="Apply the upgrades.")
    args = parser.parse_args()
    return upgrade_every_store(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
