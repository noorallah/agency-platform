"""`create-database` on a real server: a first install, then an upgrade.

The installer runs this step on every install *and* every upgrade. An upgrade
has no superuser password to hand, so the step signs in as the application's own
account -- and PostgreSQL lets a role change its own password but not its LOGIN
attribute. `ALTER ROLE ... WITH LOGIN PASSWORD` was refused there, which stopped
the configure step before the migrations on every upgrade, inside a Setup window
nobody could see. SQLite has no roles, so only this suite can see it.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url

from app.core.config.settings import Settings
from app.core.database.bootstrap import ensure_role_and_database
from app.core.database.config import database_config_from_settings


@pytest.fixture
def superuser_url(engine: Engine) -> URL:
    """Return the configured account's URL, skipping unless it is a superuser."""
    with engine.connect() as connection:
        is_superuser = connection.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar()
    if not is_superuser:
        pytest.skip("creating roles and databases needs a superuser account")
    return make_url(database_config_from_settings(Settings()).url)


@pytest.fixture
def fresh_install(
    superuser_url: URL, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[str, str]]:
    """Point the settings at a role and database that do not exist yet.

    Yields the role and database names, and drops both afterwards.
    """
    suffix = uuid4().hex[:8]
    role, database = f"zz_boot_{suffix}", f"zz_boot_{suffix}"
    monkeypatch.setenv("AGENCY_DATABASE_USERNAME", role)
    monkeypatch.setenv("AGENCY_DATABASE_PASSWORD", f"pw-{suffix}")
    monkeypatch.setenv("AGENCY_DATABASE_NAME", database)
    monkeypatch.delenv("INSTALL_ADMIN_USER", raising=False)
    monkeypatch.delenv("INSTALL_ADMIN_PASSWORD", raising=False)
    try:
        yield role, database
    finally:
        cleanup = create_engine(
            superuser_url.set(database="postgres").render_as_string(
                hide_password=False
            ),
            isolation_level="AUTOCOMMIT",
        )
        with cleanup.connect() as connection:
            connection.execute(
                text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
            )
            connection.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        cleanup.dispose()


def test_an_upgrade_with_no_superuser_password_still_succeeds(
    superuser_url: URL, fresh_install: tuple[str, str]
) -> None:
    """The first run creates both; a run as the application account passes."""
    role, database = fresh_install

    first = ensure_role_and_database(
        admin_user=superuser_url.username, admin_password=superuser_url.password
    )
    assert (first.role, first.role_created) == (role, True)
    assert (first.database, first.database_created) == (database, True)

    # What Setup does on an upgrade: no administrator account at all.
    again = ensure_role_and_database()
    assert (again.role, again.role_created) == (role, False)
    assert (again.database, again.database_created) == (database, False)


def test_a_superuser_rerun_resets_the_role_password(
    superuser_url: URL, fresh_install: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-install that wrote a new password must move the role to it."""
    role, database = fresh_install
    admin = {
        "admin_user": superuser_url.username,
        "admin_password": superuser_url.password,
    }
    ensure_role_and_database(**admin)

    monkeypatch.setenv("AGENCY_DATABASE_PASSWORD", "a-new-password")
    ensure_role_and_database(**admin)

    signed_in = create_engine(
        superuser_url.set(
            database=database, username=role, password="a-new-password"
        ).render_as_string(hide_password=False)
    )
    with signed_in.connect() as connection:
        assert connection.execute(text("SELECT current_user")).scalar() == role
    signed_in.dispose()
