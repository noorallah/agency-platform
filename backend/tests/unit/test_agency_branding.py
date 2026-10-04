"""The agency's branding (backlog 71, U2): one record, read before sign-in.

The sign-in screen shows the agency's name and logo before anybody has signed
in, so the two reads are public and the writes need ``PLATFORM_SETTINGS``.
"""

import asyncio
import io
from collections.abc import Callable

import pytest
from fastapi import Response, UploadFile
from fastapi.dependencies.models import Dependant
from fastapi.dependencies.utils import get_dependant
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branding.api.router import (
    delete_branding_logo,
    get_branding,
    get_branding_logo,
    update_branding,
    upload_branding_logo,
)
from app.branding.models import AgencyBranding
from app.branding.schemas import AgencyBrandingWrite
from app.branding.services import MAX_LOGO_BYTES
from app.common.audit.models import AuditLog
from app.core.config.settings import Environment, Settings
from app.core.database.base import Base
from app.core.database.dependencies import _is_platform_path
from app.core.enums import TokenType
from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.core.tenancy.lifecycle import PLATFORM_STORE_TABLES
from app.main import create_app

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _session() -> Session:
    """Build an in-memory store holding the whole schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _principal() -> Principal:
    """Return a caller holding the platform settings permission."""
    return Principal(
        subject="admin",
        roles=frozenset({"PLATFORM_ADMIN"}),
        permissions=frozenset({"PLATFORM_SETTINGS"}),
        claims=TokenClaims(
            sub="admin", type=TokenType.ACCESS, iat=1, exp=4_102_444_800
        ),
    )


def _save(session: Session, version: int | None = None, **values: object) -> None:
    """Save the name, tagline and colour as an administrator would."""
    payload: dict[str, object] = {"agency_name": "Sri Lakshmi Agencies"}
    payload.update(values)
    update_branding(
        AgencyBrandingWrite.model_validate(payload),
        _principal(),
        Response(),
        version,
        session,
    )


def _upload(session: Session, content: bytes, version: int | None = None) -> None:
    """Send a logo file through the upload endpoint."""
    asyncio.run(
        upload_branding_logo(
            UploadFile(io.BytesIO(content), filename="logo.png"),
            _principal(),
            Response(),
            version,
            session,
        )
    )


def test_unset_branding_reads_as_not_set() -> None:
    """Before anybody gives it, the desktop keeps its own branding.json."""
    session = _session()
    answer = get_branding(Response(), session).data
    assert answer is not None
    assert answer.is_set is False
    assert answer.agency_name is None
    with pytest.raises(ResourceNotFoundError):
        get_branding_logo(session)


def test_first_save_creates_the_record_and_later_saves_replace_it() -> None:
    """One live row, whatever the number of saves."""
    session = _session()
    _save(session, tagline="  Wholesale since 1998 ", accent_color="#0a7c66")
    _save(session, agency_name=" Lakshmi Traders ", tagline="", accent_color="#0a7c66")

    assert len(session.scalars(select(AgencyBranding)).all()) == 1
    response = Response()
    answer = get_branding(response, session).data
    assert answer is not None
    assert answer.is_set is True
    assert answer.agency_name == "Lakshmi Traders"
    assert answer.tagline is None
    assert answer.accent_color == "#0A7C66"
    assert response.headers["ETag"] == f'"{answer.version}"'


def test_every_change_is_audited_without_copying_the_image() -> None:
    """The trail records the logo by type and size, not by its bytes."""
    session = _session()
    _save(session)
    _save(session, tagline="Many lights")
    _upload(session, _PNG)

    actions = [row.action for row in session.scalars(select(AuditLog))]
    assert actions == [
        "agency_branding.created",
        "agency_branding.updated",
        "agency_branding.logo_changed",
    ]
    for row in session.scalars(select(AuditLog)):
        assert "logo" not in (row.after_data or {})
    logo_row = session.scalars(
        select(AuditLog).where(AuditLog.action == "agency_branding.logo_changed")
    ).one()
    assert logo_row.after_data is not None
    assert logo_row.after_data["logo_content_type"] == "image/png"
    assert logo_row.after_data["logo_bytes"] == len(_PNG)


def test_a_resave_of_the_same_values_writes_no_audit_row() -> None:
    """A save that changes nothing is not an event."""
    session = _session()
    _save(session)
    _save(session)
    assert len(session.scalars(select(AuditLog)).all()) == 1


def test_logo_is_served_with_its_own_type() -> None:
    """The image comes back as given, typed from its bytes."""
    session = _session()
    _save(session)
    _upload(session, _JPG)
    logo = get_branding_logo(session)
    assert logo.body == _JPG
    assert logo.media_type == "image/jpeg"
    answer = get_branding(Response(), session).data
    assert answer is not None
    assert answer.has_logo is True


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "empty"),
        (b"just text pretending to be a png", "PNG or JPG"),
        (b"GIF89a" + b"\x00" * 10, "PNG or JPG"),
        (_PNG + b"\x00" * MAX_LOGO_BYTES, "1024 KB"),
    ],
    ids=["empty", "text", "gif", "too-large"],
)
def test_a_logo_that_is_not_a_small_png_or_jpg_is_refused(
    content: bytes, message: str
) -> None:
    """The bytes decide, not the filename; and the logo stays at most 1 MB."""
    session = _session()
    _save(session)
    with pytest.raises(ValidationError, match=message):
        _upload(session, content)
    assert session.scalars(select(AgencyBranding)).one().logo is None


def test_a_logo_needs_the_name_first() -> None:
    """The logo belongs to a record that names the agency."""
    session = _session()
    with pytest.raises(BusinessRuleError):
        _upload(session, _PNG)


def test_removing_the_logo_leaves_the_name() -> None:
    """The desktop shows the agency's initials when there is no logo."""
    session = _session()
    _save(session)
    _upload(session, _PNG)
    delete_branding_logo(_principal(), Response(), None, session)
    answer = get_branding(Response(), session).data
    assert answer is not None
    assert answer.has_logo is False
    assert answer.agency_name == "Sri Lakshmi Agencies"


def test_a_stale_version_is_refused() -> None:
    """Two administrators editing at once: the second is told, not overwritten."""
    session = _session()
    _save(session)
    stale = session.scalars(select(AgencyBranding)).one().version
    _save(session, stale, tagline="First")
    with pytest.raises(ConflictError):
        _save(session, stale, tagline="Second")
    with pytest.raises(ConflictError):
        _upload(session, _PNG, stale)


def test_the_database_holds_one_live_row() -> None:
    """Two first saves at once cannot both insert."""
    session = _session()
    session.add(AgencyBranding(agency_name="A"))
    session.commit()
    session.add(AgencyBranding(agency_name="B"))
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    "value",
    [{"agency_name": "   "}, {"agency_name": "A", "accent_color": "blue"}],
)
def test_a_blank_name_or_a_bad_colour_is_refused(value: dict[str, object]) -> None:
    """The name is required; the colour is #RRGGBB."""
    with pytest.raises(ValueError):
        AgencyBrandingWrite.model_validate(value)


def test_branding_lives_in_the_platform_store() -> None:
    """Sign-in reads it before a firm is chosen, so no firm store holds it."""
    assert "agency_branding" in PLATFORM_STORE_TABLES
    assert _is_platform_path("/api/v1/branding")
    assert _is_platform_path("/api/v1/branding/logo")


def _calls(dependant: Dependant) -> list[Callable[..., object]]:
    """List every dependency a route resolves, however deeply nested."""
    found: list[Callable[..., object]] = []
    for child in dependant.dependencies:
        if child.call is not None:
            found.append(child.call)
        found.extend(_calls(child))
    return found


def test_reads_need_no_sign_in_and_writes_need_platform_settings() -> None:
    """The sign-in screen reads it signed out; nobody changes it signed out."""
    application = create_app(
        Settings(
            environment=Environment.TESTING,
            bootstrap_admin_password="test-bootstrap-password",
        )
    )
    # Routers are mounted lazily, so a route may sit behind `original_router`
    # -- the same walk `test_platform_only_routes.py` makes.
    candidates: list[object] = []
    for route in application.routes:
        nested = getattr(route, "original_router", None)
        candidates.extend(nested.routes if nested is not None else [route])
    routes = {
        (method, route.path): route
        for route in candidates
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/branding")
        for method in route.methods
    }
    assert set(routes) == {
        ("GET", "/api/v1/branding"),
        ("GET", "/api/v1/branding/logo"),
        ("PUT", "/api/v1/branding"),
        ("PUT", "/api/v1/branding/logo"),
        ("DELETE", "/api/v1/branding/logo"),
    }
    for (method, _path), route in routes.items():
        dependant = get_dependant(path=route.path, call=route.endpoint)
        names = {
            getattr(call, "__qualname__", type(call).__name__)
            for call in _calls(dependant)
        }
        guarded = any("require_permission" in name for name in names)
        principal = any("principal" in name.lower() for name in names)
        if method == "GET":
            assert not guarded and not principal, (method, _path, names)
        else:
            assert guarded, (method, _path, names)
