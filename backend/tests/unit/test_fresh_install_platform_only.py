"""A fresh install holds the platform store only; the first shared firm builds its own.

What changed: ``migrate-all`` used to build ``firm_shared`` at install, and the
platform schema carried empty copies of every firm-owned table. Now a database
with no firm migrates the platform alone and prunes the firm tables out of it,
and the shared store is built by the first SHARED firm through provisioning.

Nothing here connects to a database -- each step that would is replaced, and
what is checked is which steps run, in what order, against which store.
``tests/integration/test_fresh_install.py`` runs the real thing on PostgreSQL.
"""

from collections.abc import Callable
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import cli
from app.core.database.config import PostgreSQLConfig
from app.core.database.engine import DatabaseManager
from app.core.tenancy import TenantStorageLifecycleService
from app.core.tenancy import lifecycle as tenancy_lifecycle
from app.core.tenancy import migrations as tenancy_migrations
from app.core.tenancy.lifecycle import _PLATFORM_TABLES, PLATFORM_STORE_TABLES
from app.core.tenancy.migrations import MigrationTarget


def _lifecycle(
    shared_database_name: str | None = None,
) -> TenantStorageLifecycleService:
    """Build the lifecycle over a platform database it never connects to."""
    return TenantStorageLifecycleService(
        DatabaseManager(
            PostgreSQLConfig(
                host="localhost",
                port=5432,
                database="agency_platform",
                username="postgres",
                password="postgres",
                pool_size=1,
                max_overflow=0,
                pool_recycle_seconds=1800,
                default_schema="platform",
            )
        ),
        shared_database_name=shared_database_name,
        shared_schema_name="firm_shared",
    )


def _record_steps(
    lifecycle: TenantStorageLifecycleService, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, str]]:
    """Replace every step that touches a server with one that records itself."""
    steps: list[tuple[str, str]] = []

    def recorder(name: str) -> Callable[..., None]:
        """Return a stand-in step that records its target."""

        def step(*args: object, **kwargs: object) -> None:
            """Record the step and the schema or database it was given."""
            target = kwargs.get("schema_name") or (args[1] if len(args) > 1 else "")
            steps.append((name, str(target)))

        return step

    for name in (
        "_create_database_if_missing",
        "_create_schema_if_missing",
        "_run_migrations",
        "_prune_platform_objects",
    ):
        monkeypatch.setattr(lifecycle, name, recorder(name))
    return steps


def test_the_platform_keeps_its_own_tables_the_version_table_and_its_trail() -> None:
    """`audit_logs` stays: platform administration writes its own trail."""
    assert set(_PLATFORM_TABLES) < PLATFORM_STORE_TABLES
    assert PLATFORM_STORE_TABLES - set(_PLATFORM_TABLES) == {
        "alembic_version",
        "audit_logs",
    }


def test_provisioning_a_shared_firm_builds_the_shared_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema, migration, then the platform tables pruned -- as a dedicated one."""
    lifecycle = _lifecycle()
    steps = _record_steps(lifecycle, monkeypatch)
    firm = SimpleNamespace(
        id=uuid4(),
        deployment_mode="SHARED",
        database_name=None,
        schema_name=None,
        database_type="postgresql",
        connection_profile=None,
    )

    lifecycle.provision_new_firm(firm)  # type: ignore[arg-type]

    # The shared store sits in the platform's database: nothing to create
    # there but the schema.
    assert steps == [
        ("_create_schema_if_missing", "firm_shared"),
        ("_run_migrations", "firm_shared"),
        ("_prune_platform_objects", "firm_shared"),
    ]


def test_a_shared_store_in_its_own_database_creates_that_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`AGENCY_TENANCY_SHARED_DATABASE_NAME` may name another database."""
    lifecycle = _lifecycle(shared_database_name="agency_shared")
    steps = _record_steps(lifecycle, monkeypatch)

    assert lifecycle.provision_shared_store() is True

    assert steps[0] == ("_create_database_if_missing", "agency_shared")


def test_a_built_shared_store_is_left_alone_when_only_missing_is_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Firm creation asks only-if-missing, so the second shared firm is free."""
    lifecycle = _lifecycle()
    steps = _record_steps(lifecycle, monkeypatch)
    monkeypatch.setattr(tenancy_lifecycle, "store_is_built", lambda **_: True)

    assert lifecycle.provision_shared_store(only_if_missing=True) is False
    assert steps == []


def _fake_migrate_all(
    monkeypatch: pytest.MonkeyPatch, firms: int | None
) -> dict[str, object]:
    """Run `upgrade_every_store` with every server step replaced."""
    seen: dict[str, object] = {"upgraded": [], "pruned": []}
    platform = MigrationTarget("platform", "postgresql://p/agency", "platform")
    shared = MigrationTarget("shared", "postgresql://p/agency", "firm_shared")

    class _Platform:
        """Stand in for the platform database manager."""

        def dispose(self) -> None:
            """Nothing to release."""

    def targets(
        _platform: object, _settings: object, *, platform_only: bool = False
    ) -> list[MigrationTarget]:
        """Return the stores the real enumeration would, by the flag."""
        seen["platform_only"] = platform_only
        return [platform] if platform_only else [platform, shared]

    def upgrade(*, database_url: str, schema_name: str) -> None:
        """Record an upgrade."""
        upgraded = seen["upgraded"]
        assert isinstance(upgraded, list)
        upgraded.append(schema_name)

    def prune(*, database_url: str, schema_name: str) -> list[str]:
        """Record a prune of the platform store."""
        pruned = seen["pruned"]
        assert isinstance(pruned, list)
        pruned.append(schema_name)
        return ["products"]

    monkeypatch.setattr(
        tenancy_migrations.DatabaseManager, "from_settings", lambda _s: _Platform()
    )
    monkeypatch.setattr(tenancy_migrations, "count_firms", lambda _p: firms)
    monkeypatch.setattr(tenancy_migrations, "migration_targets", targets)
    monkeypatch.setattr(tenancy_migrations, "upgrade_store", upgrade)
    monkeypatch.setattr(tenancy_lifecycle, "prune_firm_objects", prune)
    lines: list[str] = []
    seen["exit"] = tenancy_migrations.upgrade_every_store(
        dry_run=False, report=lines.append
    )
    seen["lines"] = lines
    return seen


@pytest.mark.parametrize("firms", [None, 0])
def test_a_fresh_install_migrates_and_prunes_the_platform_only(
    monkeypatch: pytest.MonkeyPatch, firms: int | None
) -> None:
    """No registry yet, or one holding no firm: the platform store alone."""
    seen = _fake_migrate_all(monkeypatch, firms)

    assert seen["exit"] == 0
    assert seen["platform_only"] is True
    assert seen["upgraded"] == ["platform"]
    assert seen["pruned"] == ["platform"]


def test_an_install_with_firms_migrates_every_store_and_prunes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing installs behave exactly as before."""
    seen = _fake_migrate_all(monkeypatch, 3)

    assert seen["exit"] == 0
    assert seen["platform_only"] is False
    assert seen["upgraded"] == ["platform", "firm_shared"]
    assert seen["pruned"] == []


def test_firm_count_prints_the_number_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The installer reads one integer from stdout."""
    monkeypatch.setattr(tenancy_migrations, "count_firms", lambda _p: 2)

    assert cli.main(["firm-count"]) == 0
    assert capsys.readouterr().out.strip() == "2"


def test_firm_count_on_an_unmigrated_platform_prints_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `firms` table yet is a fresh install, and holds no firm."""
    monkeypatch.setattr(tenancy_migrations, "count_firms", lambda _p: None)

    assert cli.main(["firm-count"]) == 0
    assert capsys.readouterr().out.strip() == "0"


def test_firm_count_never_reads_an_unreachable_server_as_fresh(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unreadable server must not print 0, or the installer would proceed."""

    def unreachable(_platform: object) -> int:
        """Fail the way a stopped server does."""
        raise ConnectionError("connection refused")

    monkeypatch.setattr(tenancy_migrations, "count_firms", unreachable)

    assert cli.main(["firm-count"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "connection refused" in captured.err
