"""The one entry point a built copy of this product has.

Development is unchanged -- ``uvicorn app.main:app --reload`` and the scripts in
``scripts/`` still work and are still the documented way to run this from a
checkout. What this adds is a **single** thing to compile: a customer machine
gets ``agency-server.exe`` and no Python, so anything the product does there has
to be reachable without an interpreter and without a ``.py`` file.

The subcommands are the things an installed copy actually does::

    agency-server serve --host 0.0.0.0 --port 8000
    agency-server create-database
    agency-server migrate-all --yes
    agency-server firm-count
    agency-server purge-retention --dry-run
    agency-server --version

Each is thin. The work lives in ``app/core`` where the application can also
call it -- ``migrate-all`` and firm provisioning share ``upgrade_store``, so
there is one implementation of "upgrade a store" rather than a copy per
caller, which is the arrangement that let three stores drift a revision behind
in the first place.
"""

import argparse
import sys

from app.core.config.settings import Settings
from app.core.paths import application_root, is_compiled_build


def _serve(args: argparse.Namespace) -> int:
    """Run the HTTP server in this process."""
    # Imported here rather than at module scope: `--version` and
    # `create-database` should not pay for the whole application graph, and on
    # a machine whose database is not yet there, importing it is what fails.
    import uvicorn

    if bool(args.ssl_certfile) != bool(args.ssl_keyfile):
        # A certificate is only half of a TLS server. Refuse the
        # half-configured case rather than starting on plain HTTP while the
        # operator believes otherwise.
        print(
            "--ssl-certfile and --ssl-keyfile go together; TLS needs both.",
            file=sys.stderr,
        )
        return 2
    if not args.ssl_certfile and args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "Plain HTTP on a network interface: passwords cross the wire in "
            "clear text. Use --ssl-certfile and --ssl-keyfile on any network "
            "the firm does not control.",
            file=sys.stderr,
        )

    if args.reload and is_compiled_build():
        # Reload watches source files and re-imports them. A built copy has
        # neither the files nor `watchfiles`, so this would fail obscurely
        # several seconds in rather than here.
        print(
            "--reload needs the source tree and is not available in a built "
            "copy of this product.",
            file=sys.stderr,
        )
        return 2

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        ssl_certfile=args.ssl_certfile,
        ssl_keyfile=args.ssl_keyfile,
        reload=args.reload,
    )
    return 0


def _create_database(args: argparse.Namespace) -> int:
    """Create the application's database account and database."""
    from app.core.database.bootstrap import ensure_role_and_database

    try:
        outcome = ensure_role_and_database(
            admin_user=args.admin_user, admin_password=args.admin_password
        )
    except Exception as error:  # noqa: BLE001 - the message is the whole point
        print(f"error:{error}", file=sys.stderr)
        return 2
    # The installer parses these lines. Keep the shape.
    print(f"role-{'created' if outcome.role_created else 'updated'}:{outcome.role}")
    print(f"{'created' if outcome.database_created else 'exists'}:{outcome.database}")
    return 0


def _migrate_all(args: argparse.Namespace) -> int:
    """Upgrade every store the firm registry knows about."""
    from app.core.tenancy.migrations import upgrade_every_store

    return upgrade_every_store(dry_run=args.dry_run)


def _firm_count(args: argparse.Namespace) -> int:
    """Print how many live firms the registry holds.

    The installer runs this to tell a fresh install from an upgrade: a fresh
    install must find 0. A platform store that has not been migrated yet holds
    no firm and prints 0 too. A database that cannot be reached is an error,
    not a zero -- "could not tell" must never read as "fresh".
    """
    from app.core.database.engine import DatabaseManager
    from app.core.tenancy.migrations import count_firms

    platform = DatabaseManager.from_settings(Settings())
    try:
        count = count_firms(platform)
    except Exception as error:  # noqa: BLE001 - the message is the whole point
        print(f"error:{error}", file=sys.stderr)
        return 2
    finally:
        platform.dispose()
    print(count or 0)
    return 0


def _purge_retention(args: argparse.Namespace) -> int:
    """Apply every retention rule across every store, then the log files."""
    from app.core.logging.retention import purge_log_files
    from app.core.tenancy.retention import RetentionPolicy, purge_every_store

    if not args.dry_run:
        logs = purge_log_files(Settings())
        print(
            f"logs: {len(logs.compressed)} compressed, {len(logs.expired)} "
            f"expired, {len(logs.capped)} deleted to meet the size cap"
        )
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


def _where(args: argparse.Namespace) -> int:
    """Print what this copy is and where it thinks its files are."""
    settings = Settings()
    print(f"version:     {settings.app_version}")
    print(f"environment: {settings.environment}")
    print(f"root:        {application_root()}")
    # "compiled", not "frozen": sys.frozen is PyInstaller's marker and
    # Nuitka does not set it, which is why the first built copy of this
    # reported frozen: False while plainly being a compiled binary.
    print(f"compiled:    {is_compiled_build()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser. Separate so a test can inspect it."""
    parser = argparse.ArgumentParser(
        prog="agency-server",
        description="The Agency Platform server.",
    )
    # Read lazily from Settings rather than stamped in: the version is declared
    # once, in VERSION, and reaches here the same way it reaches /health.
    parser.add_argument(
        "--version",
        action="version",
        version=Settings().app_version,
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    serve = subcommands.add_parser("serve", help="Serve the HTTP API.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--ssl-certfile", default=None)
    serve.add_argument("--ssl-keyfile", default=None)
    serve.add_argument(
        "--reload",
        action="store_true",
        help="Restart on source changes. Development only; refused in a build.",
    )
    serve.set_defaults(handler=_serve)

    create = subcommands.add_parser(
        "create-database",
        help="Create the application database account and database.",
    )
    create.add_argument("--admin-user", default=None)
    create.add_argument("--admin-password", default=None)
    create.set_defaults(handler=_create_database)

    migrate = subcommands.add_parser("migrate-all", help="Upgrade every store to head.")
    migrate_mode = migrate.add_mutually_exclusive_group(required=True)
    migrate_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="List every store and its revision, and change nothing.",
    )
    migrate_mode.add_argument("--yes", action="store_true", help="Apply the upgrades.")
    migrate.set_defaults(handler=_migrate_all)

    firm_count = subcommands.add_parser(
        "firm-count",
        help="Print the number of live firms; 0 on a fresh install.",
    )
    firm_count.set_defaults(handler=_firm_count)

    purge = subcommands.add_parser(
        "purge-retention", help="Apply retention rules across every store."
    )
    purge.add_argument("--refresh-token-grace-days", type=int, default=7)
    purge.add_argument("--login-history-days", type=int, default=365)
    purge.add_argument("--password-history-keep", type=int, default=10)
    purge.add_argument("--execution-log-days", type=int, default=365)
    purge.add_argument("--error-report-days", type=int, default=90)
    purge_mode = purge.add_mutually_exclusive_group(required=True)
    purge_mode.add_argument(
        "--dry-run", action="store_true", help="Report counts without deleting."
    )
    purge_mode.add_argument("--yes", action="store_true", help="Apply the deletions.")
    purge.set_defaults(handler=_purge_retention)

    where = subcommands.add_parser(
        "where", help="Print the version, environment and install directory."
    )
    where.set_defaults(handler=_where)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run one subcommand."""
    args = build_parser().parse_args(argv)
    handler = args.handler
    result: int = handler(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
