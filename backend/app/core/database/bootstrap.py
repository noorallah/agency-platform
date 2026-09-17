"""Create the application's own database account and database.

The installer used to hold this as a Python program in a here-string and pipe
it into the interpreter on stdin (``$createDb | & $venv -``). That cannot work
on a machine with no interpreter, which is the machine the compiled build is
for -- so the program moved here, where it ships compiled and is reached as
``agency-server create-database``.

The privileged connection is used for this step and then forgotten. Everything
afterwards -- migrations, the server itself -- runs as the application account,
which owns its database and is not a superuser.
"""

import os
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config.settings import Settings
from app.core.database.config import database_config_from_settings


@dataclass(frozen=True, slots=True)
class BootstrapOutcome:
    """What the step did, in the words the installer prints back."""

    role: str
    role_created: bool
    database: str
    database_created: bool


def sql_literal(value: str) -> str:
    """Quote a value for DDL, which takes no bind parameters.

    PostgreSQL rejects ``CREATE ROLE ... PASSWORD :pw`` outright -- the whole
    statement fails to parse -- so the value is inlined and therefore escaped.
    The installer generates passwords from an alphabet with no quotes for the
    same reason; this is the second belt.
    """
    return "'" + value.replace("'", "''") + "'"


def ensure_role_and_database(
    *, admin_user: str | None = None, admin_password: str | None = None
) -> BootstrapOutcome:
    """Create the application role and its database if they are not there.

    ``admin_user``/``admin_password`` are a superuser account, used once. They
    fall back to the application's own credentials so that a re-run on an
    installed machine -- one where the role already exists and no superuser
    password is to hand -- still reports honestly instead of looking like a
    fresh failure. They also fall back to ``INSTALL_ADMIN_USER`` and
    ``INSTALL_ADMIN_PASSWORD``, because the installer passes them by
    environment variable rather than on the command line, where ``ps`` and the
    console history would show them.
    """
    settings = Settings()
    url = make_url(database_config_from_settings(settings).url)
    target = url.database
    app_user = url.username
    app_password = url.password
    if target is None or app_user is None:
        raise ValueError("The configured database URL names no database or user.")

    admin = url.set(
        database="postgres",
        username=admin_user or os.environ.get("INSTALL_ADMIN_USER") or app_user,
        password=(
            admin_password
            or os.environ.get("INSTALL_ADMIN_PASSWORD")
            or (app_password or "")
        ),
    )

    engine = create_engine(
        admin.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT"
    )
    try:
        with engine.connect() as connection:
            existing_role = connection.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :name"),
                {"name": app_user},
            ).scalar()
            password_sql = sql_literal(app_password or "")
            if existing_role:
                # A re-install writes a new password into .env, so the role's
                # has to follow it or the application cannot log in with the
                # file it was just given.
                connection.execute(
                    text(f'ALTER ROLE "{app_user}" WITH LOGIN PASSWORD {password_sql}')
                )
            else:
                connection.execute(
                    text(f'CREATE ROLE "{app_user}" WITH LOGIN PASSWORD {password_sql}')
                )

            existing_database = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target},
            ).scalar()
            if not existing_database:
                # Owned by the application account, so it needs no grant on
                # anything else in the cluster and no rights it does not use.
                connection.execute(
                    text(f'CREATE DATABASE "{target}" OWNER "{app_user}"')
                )
    finally:
        engine.dispose()

    return BootstrapOutcome(
        role=app_user,
        role_created=not existing_role,
        database=target,
        database_created=not existing_database,
    )
