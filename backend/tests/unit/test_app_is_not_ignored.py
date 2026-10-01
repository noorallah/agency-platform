"""No file under `app/` may be matched by a `.gitignore` pattern.

`backups/` in `backend/.gitignore` was meant for the dump folder and also
matched `app/backups/`, so #891 merged a router `main.py` imports while the
package itself was never committed. Every test passed on the machine that had
the files; the backend on `main` could not start.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


def test_no_source_file_under_app_is_git_ignored() -> None:
    """Ask git which files under `app/` it ignores; there must be none."""
    git = shutil.which("git")
    if git is None or not (BACKEND.parent / ".git").exists():
        pytest.skip("not a git checkout")
    sources = [
        str(path.relative_to(BACKEND))
        for path in (BACKEND / "app").rglob("*")
        if path.is_file() and path.suffix in {".py", ".json", ".sql"}
    ]
    result = subprocess.run(  # noqa: S603 -- fixed arguments, no shell
        [git, "check-ignore", "--no-index", "--stdin"],
        input="\n".join(sources),
        capture_output=True,
        text=True,
        cwd=BACKEND,
        check=False,
    )
    assert result.stdout.strip() == "", f"ignored by .gitignore:\n{result.stdout}"
