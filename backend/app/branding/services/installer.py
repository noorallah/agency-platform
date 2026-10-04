"""Branding typed on the server installer's Branding page (backlog 71, U1).

Setup writes what was typed to a small JSON file and runs
``agency-server set-branding --file <it>`` once the server answers. All three
fields are optional, and a branding problem must never fail an install: a
logo the server refuses is reported and skipped, and the administrator can
give it later in Settings > Platform > Branding.
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.branding.schemas import AgencyBrandingWrite
from app.branding.services.branding_service import AgencyBrandingService
from app.core.exceptions import ApplicationError


def read_installer_branding(path: Path) -> dict[str, str]:
    """Read the file Setup wrote, keeping only the three known string fields."""
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("The branding file must hold a JSON object.")
    return {
        key: value.strip()
        for key in ("agency_name", "tagline", "logo_path")
        if isinstance(value := raw.get(key), str) and value.strip()
    }


def apply_installer_branding(session: Session, values: dict[str, str]) -> list[str]:
    """Save what the installer was given and return what to tell the installer.

    Nothing is written without a name, which is what the record is; a tagline
    or logo given alone is reported as skipped. The installer's values replace
    any branding already given, since an administrator typed them just now.
    """
    name = values.get("agency_name")
    if not name:
        if values:
            return ["No agency name was given, so the tagline and logo were skipped."]
        return ["No branding was given; it can be set in Settings > Branding."]
    service = AgencyBrandingService(session)
    current = service.current()
    accent = current.accent_color if current is not None else None
    service.update(
        AgencyBrandingWrite(
            agency_name=name, tagline=values.get("tagline"), accent_color=accent
        ),
        actor_id=None,
        expected_version=None,
    )
    messages = [f"Agency branding saved: {name}."]
    logo_path = values.get("logo_path")
    if logo_path:
        try:
            content = Path(logo_path).read_bytes()
            service.set_logo(content, actor_id=None, expected_version=None)
            messages.append("Logo saved.")
        except OSError as error:
            messages.append(f"warning: the logo could not be read: {error}")
        except ApplicationError as error:
            session.rollback()
            messages.append(f"warning: the logo was not saved: {error.message}")
    return messages
