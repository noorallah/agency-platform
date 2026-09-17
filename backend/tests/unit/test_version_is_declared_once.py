"""One version, declared once, and a guard that fails when it drifts.

Six places carried a version before 2026-09-17 and none of them agreed:
`pubspec.yaml` said 1.0.0+1, `branding.json` 1.0.0 (the only one a user ever
saw), `branding_config.dart` 1.0.0 as a fallback, `pyproject.toml` 0.1.0,
`settings.app_version` 0.1.0, and the OpenAPI document reported "v1.0", which is
the *API* version and a different thing entirely.

`VERSION` at the repository root is now the source. Every other place is stamped
from it by `build/stamp_version.ps1`, and this test is what stops them drifting
apart again -- the same reasoning as `test_claude_md_names_real_things`: a fact
repeated in six files is a fact that will be wrong in five of them.

The OpenAPI version is deliberately **not** included here. It answers "which
version of the HTTP contract is this", which moves on its own schedule; the
product build is reported by `/health` instead, so an installed copy can say
what it is.
"""

import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def _version_file() -> str:
    """Return the one declared version."""
    return (_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_the_version_file_is_a_plain_release_number() -> None:
    """No build metadata, no prefix -- everything else derives from this."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", _version_file()), _version_file()


def test_the_flutter_client_carries_the_declared_version() -> None:
    """`pubspec.yaml` feeds the exe's own FileVersion through CMake."""
    pubspec = (_ROOT / "desktop" / "pubspec.yaml").read_text(encoding="utf-8")
    declared = re.search(r"^version:\s*(\S+)", pubspec, re.MULTILINE)
    assert declared is not None, "pubspec.yaml has no version:"
    # Flutter's `1.2.3+4` -- the build number after `+` is its own thing.
    assert declared.group(1).split("+")[0] == _version_file()


def test_the_branding_file_carries_the_declared_version() -> None:
    """The login screen shows this one, so a user reads it directly."""
    branding = json.loads(
        (_ROOT / "desktop" / "config" / "branding.json").read_text(encoding="utf-8")
    )
    assert branding["version"] == _version_file()


def test_the_backend_package_carries_the_declared_version() -> None:
    """`pyproject.toml` said 0.1.0 while the product said 1.0.0."""
    pyproject = (_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert declared is not None, "pyproject.toml has no version"
    assert declared.group(1) == _version_file()


def test_the_running_application_reports_the_declared_version() -> None:
    """`/health` answers "what is running here", so it must not drift either."""
    source = _ROOT / "backend" / "app" / "core" / "config" / "settings.py"
    settings = source.read_text(encoding="utf-8")
    declared = re.search(
        r'^\s*app_version:\s*str\s*=\s*"([^"]+)"', settings, re.MULTILINE
    )
    assert declared is not None, "settings.py has no app_version default"
    assert declared.group(1) == _version_file()
