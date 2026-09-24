"""No class in ``app/`` may use the PEP 695 generic-class syntax.

``class ApiResponse[PayloadT](BaseModel)`` runs under the interpreter, ruff's
``UP046`` asks for it, and the whole unit suite passes with it. Compiled by
Nuitka (4.2.1, 2026-09-24) the type parameter is written into the class body
as a plain attribute, and pydantic refuses the model at import time::

    PydanticUserError: A non-annotated attribute was detected:
    `PayloadT = PayloadT`. All model fields require a type annotation

That was the first thing the first installed copy of this product did: the
service never answered, and nothing on the developer's machine had seen it,
because ``--version`` -- the release check's one proof that the binary starts
-- imports none of the application. Two things came of it. The classic
``Generic[T]`` spelling everywhere (this guard), and ``agency-server check``,
which imports the whole application and which the build now runs.

The leak is real on every class, not only pydantic's -- a plain generic list
subclass gained a ``RowT`` attribute in the same experiment -- so the rule is
the syntax, not the base class. Generic *functions* (``def f[T](x: T)``) and
``type`` aliases compiled and ran correctly in the same experiment and stay
allowed.
"""

from __future__ import annotations

import ast
from pathlib import Path

_APP = Path(__file__).resolve().parents[2] / "app"


def _classes_with_type_params() -> list[str]:
    """Return ``path:line: ClassName`` for every generic-syntax class."""
    found: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.type_params:
                relative = path.relative_to(_APP.parent)
                found.append(f"{relative}:{node.lineno}: {node.name}")
    return found


def test_no_class_uses_pep695_type_parameters() -> None:
    """A generic class is spelled ``class C(Base, Generic[T])`` with a TypeVar."""
    offenders = _classes_with_type_params()
    assert not offenders, (
        "These classes use `class C[T](...)`, which Nuitka compiles into a "
        "stray class attribute and pydantic then refuses at import time. "
        "Spell them `T = TypeVar('T')` + `class C(Base, Generic[T])` with "
        "`# noqa: UP046`, as app/core/responses/models.py does:\n  "
        + "\n  ".join(offenders)
    )
