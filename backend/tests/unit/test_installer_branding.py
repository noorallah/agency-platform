"""Branding typed on the server installer's Branding page (backlog 71, U1).

Setup hands the page's values to ``agency-server set-branding --file``. Every
field is optional, and nothing about branding may fail an install.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branding.models import AgencyBranding
from app.branding.services.installer import (
    apply_installer_branding,
    read_installer_branding,
)
from app.core.database.base import Base

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_REPO = Path(__file__).resolve().parents[3]


def _session() -> Session:
    """Build an in-memory store holding the whole schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_the_file_setup_writes_is_read_with_its_byte_order_mark(
    tmp_path: Path,
) -> None:
    """Inno Setup writes UTF-8 with a BOM; blanks and unknown keys are dropped."""
    path = tmp_path / "branding.json"
    payload = {
        "agency_name": " Sri Lakshmi Agencies ",
        "tagline": "",
        "logo_path": "",
        "other": "ignored",
    }
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))
    assert read_installer_branding(path) == {"agency_name": "Sri Lakshmi Agencies"}


def test_name_tagline_and_logo_are_saved(tmp_path: Path) -> None:
    """What the page was given becomes the server's branding record."""
    logo = tmp_path / "logo.png"
    logo.write_bytes(_PNG)
    session = _session()
    messages = apply_installer_branding(
        session,
        {
            "agency_name": "Sri Lakshmi Agencies",
            "tagline": "Wholesale since 1998",
            "logo_path": str(logo),
        },
    )
    row = session.scalars(select(AgencyBranding)).one()
    assert (row.agency_name, row.tagline, row.logo) == (
        "Sri Lakshmi Agencies",
        "Wholesale since 1998",
        _PNG,
    )
    assert messages[-1] == "Logo saved."


@pytest.mark.parametrize(
    "logo",
    [b"not an image at all", None],
    ids=["refused-logo", "missing-file"],
)
def test_a_bad_logo_is_reported_and_the_name_still_saved(
    tmp_path: Path, logo: bytes | None
) -> None:
    """A branding problem never fails the install."""
    path = tmp_path / "logo.png"
    if logo is not None:
        path.write_bytes(logo)
    session = _session()
    messages = apply_installer_branding(
        session, {"agency_name": "Sri Lakshmi Agencies", "logo_path": str(path)}
    )
    row = session.scalars(select(AgencyBranding)).one()
    assert row.agency_name == "Sri Lakshmi Agencies"
    assert row.logo is None
    assert messages[-1].startswith("warning:")


@pytest.mark.parametrize(
    "values",
    [{}, {"tagline": "Only a tagline"}],
    ids=["nothing", "no-name"],
)
def test_without_a_name_nothing_is_written(values: dict[str, str]) -> None:
    """The name is the record; a tagline alone is skipped and said so."""
    session = _session()
    messages = apply_installer_branding(session, values)
    assert session.scalars(select(AgencyBranding)).all() == []
    assert len(messages) == 1


def test_setup_hands_the_file_to_the_server_after_it_answers() -> None:
    """The page's values travel by file to set-branding, never on a command line.

    A name like "Sri Lakshmi's" would otherwise need quoting through Inno,
    PowerShell and the program in turn.
    """
    iss = (_REPO / "packaging" / "AgencyPlatform.iss").read_text(encoding="utf-8")
    script = (_REPO / "packaging" / "server_setup.ps1").read_text(encoding="utf-8-sig")
    assert "-BrandingFile" in iss
    assert "[string]$BrandingFile" in script
    assert "'set-branding', '--file', $BrandingFile" in script
    ready = script.index("Set-AgencyBranding\n")
    assert script.index("Wait-Health -Seconds 90") < ready
