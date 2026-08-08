"""Prune expired refresh tokens and aged identity history.

Run against the platform schema, which is the only store holding these tables:

    uv run python scripts/purge_identity_history.py --dry-run
    uv run python scripts/purge_identity_history.py --yes
"""

import argparse
import sys

from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.identity.services import IdentityRetentionService


def main() -> int:
    """Report or apply the identity retention rules."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-token-grace-days",
        type=int,
        default=7,
        help="Delete tokens expired or revoked longer ago than this.",
    )
    parser.add_argument(
        "--login-history-days",
        type=int,
        default=365,
        help="Retention window for login history.",
    )
    parser.add_argument(
        "--password-history-keep",
        type=int,
        default=10,
        help="Password hashes to retain per user.",
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
        result = IdentityRetentionService(session).purge(
            refresh_token_grace_days=args.refresh_token_grace_days,
            login_history_days=args.login_history_days,
            password_history_keep=args.password_history_keep,
            dry_run=args.dry_run,
        )
    verb = "would remove" if args.dry_run else "removed"
    print(f"refresh_tokens:   {verb} {result.refresh_tokens}")
    print(f"login_history:    {verb} {result.login_history}")
    print(f"password_history: {verb} {result.password_history}")
    print(f"total:            {verb} {result.total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
