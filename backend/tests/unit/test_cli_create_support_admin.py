"""`agency-server create-support-admin` (backlog 29s, part a).

One named account holding the ALL_FIRMS designation, made only from the
command line. Run twice it changes nothing; the password reaches neither the
console nor the audit trail.
"""

import argparse
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cli import build_parser, run_create_support_admin
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.enums import PlatformAdminScope
from app.core.security import PasswordSecurity
from app.identity.models import PlatformAdmin, User

PASSWORD = "Support-Secret-42!"
OTHER_PASSWORD = "Another-Secret-77!"
EMAIL = "support@vendor.example"


@pytest.fixture
def session() -> Iterator[Session]:
    """Yield a session on a fresh in-memory schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _args(*extra: str) -> argparse.Namespace:
    """Parse a create-support-admin command line."""
    return build_parser().parse_args(["create-support-admin", "--email", EMAIL, *extra])


def _support_user(session: Session) -> User:
    """Return the one live account holding the support address."""
    user = session.scalar(
        select(User).where(User.email == EMAIL, User.is_deleted.is_(False))
    )
    assert user is not None
    return user


def test_it_creates_the_account_with_the_all_firms_designation(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A first run makes the account and its ALL_FIRMS row."""
    monkeypatch.setenv("AGENCY_SUPPORT_PASSWORD", PASSWORD)

    assert run_create_support_admin(session, _args()) == 0

    user = _support_user(session)
    designation = session.scalar(
        select(PlatformAdmin).where(PlatformAdmin.user_id == user.id)
    )
    assert designation is not None
    assert designation.scope == PlatformAdminScope.ALL_FIRMS.value
    assert user.is_active
    assert user.department == "Support"
    assert PasswordSecurity().verify_password(PASSWORD, user.password_hash)
    assert "created" in capsys.readouterr().out


def test_a_second_run_changes_nothing_and_asks_for_no_password(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Idempotent: an existing account is reported, its password untouched."""
    monkeypatch.setenv("AGENCY_SUPPORT_PASSWORD", PASSWORD)
    run_create_support_admin(session, _args())
    capsys.readouterr()

    def _no_prompt(prompt: str = "") -> str:
        """Fail if the command asks for a password it does not need."""
        raise AssertionError("prompted for a password")

    monkeypatch.delenv("AGENCY_SUPPORT_PASSWORD")
    monkeypatch.setattr("getpass.getpass", _no_prompt)

    assert run_create_support_admin(session, _args()) == 0

    users = session.scalars(select(User).where(User.email == EMAIL)).all()
    assert len(users) == 1
    assert PasswordSecurity().verify_password(PASSWORD, users[0].password_hash)
    assert len(session.scalars(select(PlatformAdmin)).all()) == 1
    assert "exists" in capsys.readouterr().out


def test_reset_password_changes_it(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--reset-password is the one way to change an existing password."""
    monkeypatch.setenv("AGENCY_SUPPORT_PASSWORD", PASSWORD)
    run_create_support_admin(session, _args())
    version = _support_user(session).authorization_version
    monkeypatch.setenv("AGENCY_SUPPORT_PASSWORD", OTHER_PASSWORD)

    assert run_create_support_admin(session, _args("--reset-password")) == 0

    user = _support_user(session)
    assert PasswordSecurity().verify_password(OTHER_PASSWORD, user.password_hash)
    assert user.authorization_version == version + 1


def test_the_prompt_must_match_twice(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two different typings create nothing."""
    monkeypatch.delenv("AGENCY_SUPPORT_PASSWORD", raising=False)
    typed = iter([PASSWORD, OTHER_PASSWORD])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(typed))

    assert run_create_support_admin(session, _args()) == 2
    assert session.scalar(select(User).where(User.email == EMAIL)) is None


def test_the_prompted_password_is_used(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same password typed twice creates the account with it."""
    monkeypatch.delenv("AGENCY_SUPPORT_PASSWORD", raising=False)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASSWORD)

    assert run_create_support_admin(session, _args()) == 0
    user = _support_user(session)
    assert PasswordSecurity().verify_password(PASSWORD, user.password_hash)


def test_the_password_is_never_printed_or_audited(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Neither the console nor the trail carries the password."""
    monkeypatch.setenv("AGENCY_SUPPORT_PASSWORD", PASSWORD)
    run_create_support_admin(session, _args())
    monkeypatch.setenv("AGENCY_SUPPORT_PASSWORD", OTHER_PASSWORD)
    run_create_support_admin(session, _args("--reset-password"))

    printed = capsys.readouterr()
    assert PASSWORD not in printed.out + printed.err
    assert OTHER_PASSWORD not in printed.out + printed.err
    rows = session.scalars(select(AuditLog)).all()
    assert {row.action for row in rows} >= {
        "identity.support_admin_created",
        "identity.support_admin_password_reset",
    }
    for row in rows:
        trail = f"{row.before_data}{row.after_data}"
        assert PASSWORD not in trail
        assert OTHER_PASSWORD not in trail


def test_a_weak_password_is_refused(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordinary password policy applies."""
    monkeypatch.setenv("AGENCY_SUPPORT_PASSWORD", "short")

    assert run_create_support_admin(session, _args()) == 2
    assert session.scalar(select(User).where(User.email == EMAIL)) is None


def test_an_ordinary_users_address_is_not_promoted(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An address held by another account is refused, not widened."""
    session.add(
        User(
            email=EMAIL,
            full_name="Somebody",
            password_hash=PasswordSecurity().hash_password(PASSWORD),
        )
    )
    session.commit()
    monkeypatch.setenv("AGENCY_SUPPORT_PASSWORD", OTHER_PASSWORD)

    assert run_create_support_admin(session, _args()) == 2
    assert run_create_support_admin(session, _args("--reset-password")) == 2
    assert session.scalars(select(PlatformAdmin)).all() == []
