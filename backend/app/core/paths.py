"""Where the application's own files are, in a checkout and in a built copy.

``alembic.ini`` declares ``script_location = alembic`` and ``prepend_sys_path =
.``, both relative, so something has to know the directory those are relative
to. Until 2026-09-17 three places each worked it out from ``__file__`` and a
``parents[n]`` count -- ``app/core/tenancy/lifecycle.py`` used ``parents[3]``,
the two scripts used ``parents[1]`` -- which is correct in a checkout and wrong
in a compiled build, where ``__file__`` names a path inside the binary that no
file was ever written to.

One answer, asked one way:

* a compiled build -- ``sys.frozen`` -- is the directory the executable is in,
  because that is where the installer put ``alembic/`` beside it;
* a checkout is ``backend/``, found from this file;
* ``AGENCY_APPLICATION_ROOT`` overrides both, for the case neither describes.

Nothing here reads a database or a setting, so it is safe to call from
anywhere, including before ``Settings()`` exists.
"""

import os
import sys
from pathlib import Path


def application_root() -> Path:
    """Return the directory holding ``alembic.ini`` and ``alembic/``."""
    override = os.environ.get("AGENCY_APPLICATION_ROOT")
    if override and override.strip():
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        # A standalone build unpacks nothing: the data files the installer
        # shipped sit next to the executable, which is what the .iss places
        # and what build_installer.ps1 stages.
        return Path(sys.executable).resolve().parent
    # app/core/paths.py -> app/core -> app -> backend
    return Path(__file__).resolve().parents[2]


def alembic_ini_path() -> Path:
    """Return the path to ``alembic.ini``."""
    return application_root() / "alembic.ini"


def alembic_script_location() -> Path:
    """Return the directory holding the migration scripts."""
    return application_root() / "alembic"
