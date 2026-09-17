"""Apply every retention rule across every store, in one command.

The two retention services exist and nothing ran them. Worse, running the tax
one *correctly* meant knowing the tenancy layout: its log is firm-owned, so it
lives in ``firm_shared``, in each dedicated schema, and inside each dedicated
database. An operator scheduling a single-schema purge would have pruned the
default schema and silently missed every other firm -- the same trap ``alembic
upgrade head`` carries, and for the same reason.

Run it with ``--dry-run`` first; it reports per store and changes nothing.

    uv run python scripts/purge_retention.py --dry-run
    uv run python scripts/purge_retention.py --yes

**The work is in ``app/core/tenancy/retention.py``**, not here -- it moved on
2026-09-17 so that a built copy, which has no interpreter to hand a script to,
can run the same sweep as ``agency-server purge-retention``.
"""

import argparse
import sys

from app.core.tenancy.retention import RetentionPolicy, purge_every_store


def main() -> int:
    """Report or apply every retention rule across every store."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-token-grace-days", type=int, default=7)
    parser.add_argument("--login-history-days", type=int, default=365)
    parser.add_argument("--password-history-keep", type=int, default=10)
    parser.add_argument("--execution-log-days", type=int, default=365)
    parser.add_argument("--error-report-days", type=int, default=90)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run", action="store_true", help="Report counts without deleting."
    )
    group.add_argument("--yes", action="store_true", help="Apply the deletions.")
    args = parser.parse_args()

    return purge_every_store(
        dry_run=args.dry_run,
        policy=RetentionPolicy(
            refresh_token_grace_days=args.refresh_token_grace_days,
            login_history_days=args.login_history_days,
            password_history_keep=args.password_history_keep,
            execution_log_days=args.execution_log_days,
            error_report_days=args.error_report_days,
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
