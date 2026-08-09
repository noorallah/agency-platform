"""Prune aged tax rule execution logs.

The log is firm-owned, so it lives in each firm's store rather than in
``platform``. Run it once per store, selecting the store the same way a
migration does -- with ``AGENCY_DATABASE_SCHEMA`` (and ``AGENCY_DATABASE_NAME``
for a firm on a dedicated database):

    uv run python scripts/purge_tax_execution_logs.py --dry-run
    $env:AGENCY_DATABASE_SCHEMA="firm_shared"
    uv run python scripts/purge_tax_execution_logs.py --yes
"""

import argparse
import sys
from uuid import UUID

from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.tax.services import TaxRetentionService


def main() -> int:
    """Report or apply the tax execution log retention rule."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execution-log-days",
        type=int,
        default=365,
        help="Retention window for tax rule execution logs.",
    )
    parser.add_argument(
        "--firm-id",
        type=UUID,
        default=None,
        help="Limit the purge to one firm instead of every firm in the store.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run", action="store_true", help="Report counts without deleting."
    )
    group.add_argument("--yes", action="store_true", help="Apply the deletions.")
    args = parser.parse_args()

    settings = Settings()
    database = DatabaseManager.from_settings(settings)
    with database.sessions(schema=settings.database_schema).session() as session:
        result = TaxRetentionService(session).purge(
            execution_log_days=args.execution_log_days,
            firm_scope=args.firm_id,
            dry_run=args.dry_run,
        )
    verb = "would remove" if args.dry_run else "removed"
    print(f"schema:                   {settings.database_schema}")
    print(f"tax_rule_execution_logs:  {verb} {result.execution_logs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
