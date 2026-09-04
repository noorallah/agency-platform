"""`CLAUDE.md` must not name a path, migration or identifier that is not there.

Every claim in that file was re-derived on 2026-09-05 and **seven were wrong**:
four counts that had drifted, a permission code offered as an example that has
never existed, a feature tally that no longer summed, and automatic GL posting
described as unbuilt while eleven modules were posting.

None was wrong when written. Each stopped being true and nobody re-derived it,
which is the failure the file warns about in its own words -- *a stale number
talks people out of running the tools at all*. A reader who finds one claim
false has no way to know which of the others still hold, so the whole file
loses its authority at once.

**What this guards, and what it deliberately does not.** Names are stable: a
file that gets renamed, a migration that gets squashed, a helper that gets
deleted are all facts a test can hold. Counts are not: a test that fails every
time somebody adds a test file becomes a test somebody deletes, and a disabled
guard is worse than none. So counts carry the date they were taken and the
command that produces them, and this checks only that the file names things
that exist.

Skips when the desktop tree is absent, so the backend suite still stands alone.
"""

# ruff: noqa: D103

import re
from functools import lru_cache
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_CLAUDE = _ROOT / "CLAUDE.md"
_BACKEND = _ROOT / "backend"
_DESKTOP = _ROOT / "desktop"

#: Anything the file puts in backticks. It uses them for paths, identifiers,
#: commands, permission codes and prose emphasis alike, so each candidate is
#: classified below rather than checked blindly.
_TICKED = re.compile(r"`([^`\n]{2,120})`")

_PATH_LIKE = re.compile(r"^[A-Za-z0-9_./-]+\.(py|dart|md|sql|ps1|sh|json|ya?ml)$")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{3,}$")
_REVISION = re.compile(r"`(\d{8}_\d{4})`")

#: Names the file mentions precisely because they are **gone**. Each is
#: historical and the sentence around it says so; removing them would delete
#: the reason a thing is not there, which is usually the more useful half.
_DELIBERATELY_ABSENT = {
    "TAX_RULE_SIMULATE": (
        "never a seeded permission code. CLAUDE.md offered it as an example "
        "of the `DOMAIN_ACTION` shape until 2026-09-05, and now names it in "
        "the section explaining what the re-derivation found -- so the "
        "sentence that says it does not exist would otherwise fail this test."
    ),
    "accounting_event_consumer.py": (
        "removed on 2026-08-09 -- it guessed ledger accounts by name. The "
        "file points at git history for its posting rules."
    ),
}

#: Words that read as identifiers and are ordinary prose or external names.
_NOT_OURS = {
    "postgresql_where",
    "sqlite_where",
    "version_id_col",
    "prefers",
    "search_path",
    "autoflush",
    "begin_nested",
    "model_dump",
    "model_fields_set",
    "exclude_unset",
    "with_for_update",
    "ondelete",
    "server_default",
    "selectin",
    "tabular",
}


@lru_cache(maxsize=1)
def _text() -> str:
    return _CLAUDE.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _ticked() -> tuple[str, ...]:
    return tuple(sorted(set(_TICKED.findall(_text()))))


@lru_cache(maxsize=1)
def _source() -> str:
    """Every source file in both applications, concatenated once.

    Read once and searched as text. A per-name grep over eleven megabytes
    would turn a fast test into a slow one for no extra precision.
    """
    chunks: list[str] = []
    for base, patterns in (
        (_BACKEND, ("**/*.py", "**/*.sql", "**/*.yml", "**/*.ps1")),
        (_DESKTOP, ("**/*.dart",)),
    ):
        if not base.exists():
            continue
        for pattern in patterns:
            for path in base.glob(pattern):
                flat = str(path).replace("\\", "/")
                if "__pycache__" in flat or "/.venv/" in flat or "/build/" in flat:
                    continue
                # Not this file. Its own prose names the very things it exists
                # to catch -- `TAX_RULE_SIMULATE` is quoted above as the
                # example -- so leaving it in the corpus lets any dead name
                # validate itself the moment somebody documents it here.
                if path.resolve() == Path(__file__).resolve():
                    continue
                try:
                    chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    continue
    return "\n".join(chunks)


@pytest.mark.skipif(not _CLAUDE.exists(), reason="CLAUDE.md not present")
def test_every_path_it_names_exists() -> None:
    missing = []
    for item in _ticked():
        if not _PATH_LIKE.match(item) or item in _DELIBERATELY_ABSENT:
            continue
        if any((base / item).exists() for base in (_ROOT, _BACKEND, _DESKTOP)):
            continue
        # A bare filename may sit anywhere in the tree.
        if any(_ROOT.rglob(Path(item).name)):
            continue
        missing.append(item)
    assert not missing, (
        "CLAUDE.md names these files and they do not exist:\n  "
        + "\n  ".join(sorted(missing))
        + "\n\nFix the path, or add it to `_DELIBERATELY_ABSENT` with the "
        "reason it is named while gone."
    )


@pytest.mark.skipif(not _CLAUDE.exists(), reason="CLAUDE.md not present")
def test_every_migration_it_names_exists() -> None:
    versions = _BACKEND / "alembic" / "versions"
    present = {
        "_".join(path.name.split("_")[:2])
        for path in versions.glob("*.py")
        if len(path.name.split("_")) > 1
    }
    named = set(_REVISION.findall(_text()))
    assert named, "the revision pattern found nothing -- the shape moved"
    absent = sorted(named - present)
    assert not absent, (
        "CLAUDE.md names these migrations and they are not in "
        "alembic/versions:\n  " + "\n  ".join(absent)
    )


@pytest.mark.skipif(not _DESKTOP.exists(), reason="desktop tree not present")
def test_every_identifier_it_names_is_findable() -> None:
    """A class, function, table, column or setting it names must exist.

    Text search rather than import: the file names tables, columns, permission
    codes and environment variables as well as Python symbols, and those live
    in migrations, seeds and compose files rather than in an importable
    namespace. `TAX_RULE_SIMULATE` was offered as an example permission code
    and appeared nowhere at all -- exactly what this catches.
    """
    body = _source()
    missing = []
    for item in _ticked():
        if _PATH_LIKE.match(item) or not _IDENT.match(item):
            continue
        if item in _NOT_OURS or item in _DELIBERATELY_ABSENT:
            continue
        if item in body:
            continue
        missing.append(item)
    assert not missing, (
        "CLAUDE.md names these and they appear nowhere in either "
        "application:\n  "
        + "\n  ".join(sorted(missing))
        + "\n\nEither the name is wrong, or the thing was removed and the "
        "sentence should say so."
    )
