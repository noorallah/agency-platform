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
    agency-server backup
    agency-server backup-copy
    agency-server backup-open --file <copy>.agbk --into <folder>
    agency-server check
    agency-server messaging-run-once
    agency-server loyalty-expire
    agency-server set-branding --file branding.json
    agency-server create-support-admin --email support@example.com
    agency-server --version

Each is thin. The work lives in ``app/core`` where the application can also
call it -- ``migrate-all`` and firm provisioning share ``upgrade_store``, so
there is one implementation of "upgrade a store" rather than a copy per
caller, which is the arrangement that let three stores drift a revision behind
in the first place.
"""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config.settings import Settings
from app.core.paths import application_root, is_compiled_build

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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

    settings = Settings()
    if args.scheduled and not settings.retention_auto_purge:
        # The nightly task asks every night; the platform said not to (PLT-6).
        print("retention: switched off (AGENCY_RETENTION_AUTO_PURGE=false)")
        return 0
    if not args.dry_run:
        logs = purge_log_files(settings)
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


def _backup(args: argparse.Namespace) -> int:
    """Back up every store into the manual backups folder, as the button does."""
    import getpass

    from app.core.tenancy.backup import BackupError, back_up_every_store

    try:
        result = back_up_every_store(
            Settings(),
            requested_by=f"agency-server backup ({getpass.getuser()})",
            report=print,
        )
    except BackupError as error:
        print(f"Backup failed: {error}", file=sys.stderr)
        return 1
    if result.failed:
        print(
            f"\n{len(result.failed)} store(s) failed; {result.folder} is not a "
            "complete backup.",
            file=sys.stderr,
        )
        return 1
    print(f"\nBackup written to {result.folder}")
    if result.second_copy is not None:
        print(result.second_copy)
    return 0


def _backup_copy(args: argparse.Namespace) -> int:
    """Bring the second backup folder up to date, as the nightly task does."""
    from app.core.tenancy.backup import BackupError
    from app.core.tenancy.backup_copy import copy_backups_to_second_folder

    settings = Settings()
    if args.backup_directory is not None:
        # The service is told its backup folder by its own definition, which
        # a scheduled task does not read; the task names the folder instead.
        settings = settings.model_copy(
            update={"backup_directory": args.backup_directory}
        )
    try:
        result = copy_backups_to_second_folder(settings, report=print)
    except BackupError as error:
        print(f"Second copy failed: {error}", file=sys.stderr)
        return 1
    if result is None:
        print(
            "No second backup folder is set (AGENCY_BACKUP_SECOND_DIRECTORY), "
            "so no second copy is kept."
        )
        return 0
    print(result.summary())
    return 1 if result.failed else 0


def _backup_open(args: argparse.Namespace) -> int:
    """Turn one protected copy back into a folder of dumps."""
    import getpass

    from app.core.tenancy.backup import BackupError
    from app.core.tenancy.backup_copy import open_copy

    if args.password_file is not None:
        try:
            lines = args.password_file.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            print(f"Could not read {args.password_file}: {error}", file=sys.stderr)
            return 1
        password = lines[0] if lines else ""
    else:
        password = getpass.getpass("Password of the backup copy: ")
    try:
        names = open_copy(args.file, args.into, password=password)
    except BackupError as error:
        print(f"Not opened: {error}", file=sys.stderr)
        return 1
    print(f"{len(names)} file(s) written to {args.into}:")
    for name in names:
        print(f"  {name}")
    return 0


def _check(args: argparse.Namespace) -> int:
    """Import the whole application and report that it can be built.

    ``--version`` proves the binary starts; it does not prove the product in
    it works, because it imports none of the application. The first installed
    copy of this product passed ``--version`` on the build machine and then
    failed on the customer's, at the first pydantic model it imported -- a
    defect that only a compiled build can show (2026-09-24). This is the
    check the build runs instead: it constructs the FastAPI application
    exactly as ``serve`` would, which imports every router, model and
    service, and needs no database to do it. A failure is the traceback.
    """
    # Imported here for the same reason `serve` does it: the graph is the
    # thing under test, and `--version` should not pay for it.
    from app.main import create_app

    application = create_app()
    # The OpenAPI document walks every route's request and response schema,
    # so a model that pydantic would refuse, or a field it cannot describe,
    # fails here rather than on a customer's first request.
    paths = application.openapi()["paths"]
    print(f"ok: application built, {len(paths)} paths")
    return 0


def _messaging_run_once(args: argparse.Namespace) -> int:
    """Run one messaging pass over every firm: send, retry, remind, fetch status.

    The server does this on a timer in its own process; this is the same pass
    for an operator who wants it now, or a test that wants it once. Exits
    non-zero when a firm's store could not be reached.
    """
    from app.core.database.engine import DatabaseManager
    from app.core.tenancy import (
        FirmConnectionResolver,
        FirmRegistryTenantResolver,
        FirmSchemaResolver,
        MultiTenantDatabaseProvider,
    )
    from app.messaging.services.outbox_worker import process_every_firm
    from app.messaging.services.runtime import live_firm_ids, store_opener

    settings = Settings()
    platform = DatabaseManager.from_settings(settings)
    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    resolver = FirmRegistryTenantResolver(
        platform,
        shared_database_name=settings.tenancy.shared_database_name,
        shared_schema_name=settings.tenancy.shared_schema_name,
    )
    try:
        report = process_every_firm(
            live_firm_ids(platform), store_opener(resolver, provider)
        )
    finally:
        provider.dispose()
        platform.dispose()
    print(
        f"sent: {report.sent}, failed: {report.failed}, retrying: "
        f"{report.retried}, held for an IRN: {report.held}, "
        f"reminders queued: {report.reminders}, skipped: "
        f"{report.skipped}, statuses: {report.statuses}"
    )
    for error in report.errors:
        print(f"error:{error}", file=sys.stderr)
    return 1 if report.errors else 0


def _loyalty_expire(args: argparse.Namespace) -> int:
    """Lapse loyalty points that have run out of time, in every firm.

    The sweep ``POST /api/v1/loyalty/expire`` runs for one firm, over every
    firm's own store, for an operator or whatever schedules it: nothing ran
    it, so a firm that never pressed the button never released the cost of a
    lapsed point (D-PRC-3). Prints one line per firm and exits non-zero when
    a firm's store could not be reached.
    """
    from app.core.database.engine import DatabaseManager
    from app.core.tenancy import (
        FirmConnectionResolver,
        FirmRegistryTenantResolver,
        FirmSchemaResolver,
        MultiTenantDatabaseProvider,
    )
    from app.loyalty.services.expiry_sweep import sweep_every_firm
    from app.messaging.services.runtime import live_firm_ids, store_opener

    settings = Settings()
    platform = DatabaseManager.from_settings(settings)
    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    resolver = FirmRegistryTenantResolver(
        platform,
        shared_database_name=settings.tenancy.shared_database_name,
        shared_schema_name=settings.tenancy.shared_schema_name,
    )
    try:
        report = sweep_every_firm(
            live_firm_ids(platform), store_opener(resolver, provider)
        )
    finally:
        provider.dispose()
        platform.dispose()
    for firm_id, lapsed in report.lapsed.items():
        print(f"firm {firm_id}: {lapsed} batches lapsed")
    print(
        f"loyalty: {sum(report.lapsed.values())} batches lapsed in "
        f"{len(report.lapsed)} firms, {len(report.errors)} not reached"
    )
    for error in report.errors:
        print(f"error:{error}", file=sys.stderr)
    return 1 if report.errors else 0


def _set_branding(args: argparse.Namespace) -> int:
    """Save the agency's branding typed on the installer's Branding page.

    A branding problem never fails an install: an unreadable file is an error
    (Setup logs it as a warning), but a refused logo is reported and the name
    is still saved.
    """
    from pathlib import Path

    from app.branding.services.installer import (
        apply_installer_branding,
        read_installer_branding,
    )
    from app.core.database.engine import DatabaseManager

    try:
        values = read_installer_branding(Path(args.file))
    except (OSError, ValueError) as error:
        print(f"error: the branding file could not be read: {error}", file=sys.stderr)
        return 2
    platform = DatabaseManager.from_settings(Settings())
    try:
        schema = platform.config.default_schema or "platform"
        with platform.sessions(schema=schema).session() as session:
            for message in apply_installer_branding(session, values):
                print(message)
    finally:
        platform.dispose()
    return 0


def _support_password(email: str) -> str | None:
    """Read the support password from the environment or the console.

    ``AGENCY_SUPPORT_PASSWORD`` serves a scripted install; otherwise it is
    typed twice at a prompt that does not echo. It is never printed.
    """
    import getpass
    import os

    from_env = os.environ.get("AGENCY_SUPPORT_PASSWORD")
    if from_env:
        return from_env
    first = getpass.getpass(f"Password for {email}: ")
    second = getpass.getpass("Type it again: ")
    if first != second:
        print("error: the two passwords differ; nothing changed.", file=sys.stderr)
        return None
    return first


def _create_support_admin(args: argparse.Namespace) -> int:
    """Create the one named support account with the ALL_FIRMS designation.

    The only way the account is made (backlog 29s): no API route or screen
    creates it. Run again, it reports the account and changes nothing unless
    ``--reset-password`` is given.
    """
    from app.core.database.engine import DatabaseManager

    platform = DatabaseManager.from_settings(Settings())
    try:
        schema = platform.config.default_schema or "platform"
        with platform.sessions(schema=schema).session() as session:
            return run_create_support_admin(session, args)
    finally:
        platform.dispose()


def run_create_support_admin(session: "Session", args: argparse.Namespace) -> int:
    """Do the work of ``create-support-admin`` on an open platform session.

    Separate from the handler so a test can hand it an in-memory session.
    """
    from sqlalchemy import select

    from app.core.exceptions import ApplicationError
    from app.core.validation import validate_email
    from app.identity.models import User
    from app.identity.services.support_admin import (
        SupportAdminOutcome,
        ensure_support_admin,
    )

    try:
        email = validate_email(args.email)
        # Asked first without a password, so an account that is already there
        # is reported without prompting for a password it will not use.
        exists = session.scalar(
            select(User.id).where(User.email == email, User.is_deleted.is_(False))
        )
        password: str | None = None
        if args.reset_password or exists is None:
            password = _support_password(email)
            if password is None:
                return 2
        result = ensure_support_admin(
            session,
            email=email,
            full_name=args.full_name,
            password=password,
            reset_password=args.reset_password,
        )
    except ApplicationError as error:
        print(f"error: {error.message}", file=sys.stderr)
        return 2
    if result.outcome is SupportAdminOutcome.CREATED:
        print(f"created: {result.email} (ALL_FIRMS administrator)")
    elif result.outcome is SupportAdminOutcome.PASSWORD_RESET:
        print(f"password-reset: {result.email}")
    else:
        print(
            f"exists: {result.email}; password unchanged "
            "(--reset-password to change it)"
        )
    return 0


def _quick_check(args: argparse.Namespace) -> int:
    """Check this installation end to end, read only, and write an HTML page.

    The owner's sanity check (2026-10-02): the server answers, a person signs
    in, every store is at the newest migration, and every list and report a
    firm's screens open comes back, for every firm the person can open. Exit
    code 1 when anything failed.
    """
    import getpass
    import os
    from pathlib import Path

    from app.diagnostics.quick_check import run_quick_check, summary, write_html

    password = args.password or os.environ.get("AGENCY_QUICK_CHECK_PASSWORD")
    if not password:
        password = getpass.getpass(f"Password for {args.email}: ")
    report = run_quick_check(
        base_url=args.base_url,
        email=args.email,
        password=password,
        firm_codes=args.firm or None,
        check_stores=not args.no_stores,
        timeout=args.timeout,
        # Flushed per line: a run takes minutes, and a silent console reads
        # as a hung one.
        say=lambda line: print(line, flush=True),
    )
    print(summary(report))
    target = Path(args.report or f"quick-check-{report.started:%Y%m%d-%H%M}.html")
    print(f"Report: {write_html(report, target).resolve()}")
    return 1 if report.failed else 0


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
    purge.add_argument(
        "--scheduled",
        action="store_true",
        help="Run as the nightly task does: skipped when "
        "AGENCY_RETENTION_AUTO_PURGE is false.",
    )
    purge_mode = purge.add_mutually_exclusive_group(required=True)
    purge_mode.add_argument(
        "--dry-run", action="store_true", help="Report counts without deleting."
    )
    purge_mode.add_argument("--yes", action="store_true", help="Apply the deletions.")
    purge.set_defaults(handler=_purge_retention)

    backup = subcommands.add_parser(
        "backup", help="Back up every store now, into <backup dir>/manual."
    )
    backup.set_defaults(handler=_backup)

    backup_copy = subcommands.add_parser(
        "backup-copy",
        help=(
            "Copy every finished backup the second folder lacks, "
            "password-protected, and remove the copies past their days."
        ),
    )
    backup_copy.add_argument(
        "--backup-directory",
        type=Path,
        default=None,
        help="The backup folder to copy from, when not the configured one.",
    )
    backup_copy.set_defaults(handler=_backup_copy)

    backup_open = subcommands.add_parser(
        "backup-open",
        help="Unpack one password-protected backup copy into a folder of dumps.",
    )
    backup_open.add_argument("--file", type=Path, required=True)
    backup_open.add_argument("--into", type=Path, required=True)
    backup_open.add_argument(
        "--password-file",
        type=Path,
        default=None,
        help="A file whose first line is the password; asked for when absent.",
    )
    backup_open.set_defaults(handler=_backup_open)

    where = subcommands.add_parser(
        "where", help="Print the version, environment and install directory."
    )
    where.set_defaults(handler=_where)

    check = subcommands.add_parser(
        "check", help="Import the whole application; the build's start-up proof."
    )
    check.set_defaults(handler=_check)

    quick = subcommands.add_parser(
        "quick-check",
        help=(
            "Check the running server end to end, read only: sign-in, stores, "
            "and every list and report of every firm."
        ),
    )
    quick.add_argument("--base-url", default="http://127.0.0.1:8000")
    quick.add_argument("--email", required=True, help="Who to sign in as.")
    quick.add_argument(
        "--password",
        default=None,
        help="Asked for if not given (or set AGENCY_QUICK_CHECK_PASSWORD).",
    )
    quick.add_argument(
        "--firm",
        action="append",
        default=[],
        help="A firm code to check; repeat for several. Every firm if omitted.",
    )
    quick.add_argument(
        "--no-stores",
        action="store_true",
        help="Skip the store migration check (when run away from the server).",
    )
    quick.add_argument("--timeout", type=float, default=60.0)
    quick.add_argument("--report", default=None, help="Where to write the HTML.")
    quick.set_defaults(handler=_quick_check)

    messaging = subcommands.add_parser(
        "messaging-run-once",
        help="Send queued messages and reminders for every firm, once.",
    )
    messaging.set_defaults(handler=_messaging_run_once)

    loyalty = subcommands.add_parser(
        "loyalty-expire",
        help="Lapse loyalty points that have run out of time, in every firm.",
    )
    loyalty.set_defaults(handler=_loyalty_expire)

    branding = subcommands.add_parser(
        "set-branding",
        help="Save the agency's name, tagline and logo given to Setup.",
    )
    branding.add_argument(
        "--file",
        required=True,
        help="JSON with agency_name, tagline and logo_path, all optional.",
    )
    branding.set_defaults(handler=_set_branding)

    support = subcommands.add_parser(
        "create-support-admin",
        help=(
            "Create the one named support account (ALL_FIRMS administrator); "
            "reports it and changes nothing if it exists."
        ),
    )
    support.add_argument(
        "--email", required=True, help="The support account's sign-in address."
    )
    support.add_argument("--full-name", default="Support")
    support.add_argument(
        "--reset-password",
        action="store_true",
        help="Set a new password on the existing support account.",
    )
    support.set_defaults(handler=_create_support_admin)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run one subcommand."""
    args = build_parser().parse_args(argv)
    handler = args.handler
    result: int = handler(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
