"""Print the table catalogue in `docs/TABLE_CATALOGUE.md` form.

Every fact here is read from the ORM metadata and the models themselves --
which table exists, which module declares it, where it physically lives, what
it points at -- so the document can be regenerated rather than maintained. A
hand-kept list of 198 tables is a list that rots, and this repository has the
scars to prove it.

    uv run python scripts/dump_table_catalogue.py

It writes `docs/TABLE_CATALOGUE.md` itself, in UTF-8, rather than printing for
redirection: PowerShell would re-encode the output in the console codepage and
mangle every non-ASCII character on the way through.

The one thing not derived is the prose at the top, which is kept in
``_PREAMBLE`` here so the whole file is one artefact.
"""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import Table  # noqa: E402
from sqlalchemy.orm import DeclarativeBase  # noqa: E402

import app.core.database.all_models  # noqa: E402, F401
from app.core.database.base import Base  # noqa: E402
from app.core.database.entity import BaseEntity  # noqa: E402
from app.core.tenancy.lifecycle import _PLATFORM_TABLES  # noqa: E402


def _models_by_table() -> dict[str, type[DeclarativeBase]]:
    """Map each table name to the mapped class that declares it."""
    found: dict[str, type[DeclarativeBase]] = {}
    for mapper in Base.registry.mappers:
        model = mapper.class_
        table = getattr(model, "__tablename__", None)
        if table:
            found[table] = model
    return found


def _summary(model: type[DeclarativeBase]) -> str:
    """Return the model's own one-line description, taken from its docstring."""
    doc = (model.__doc__ or "").strip()
    if not doc:
        return ""
    first = doc.split("\n\n")[0].replace("\n", " ").strip()
    return " ".join(first.split())


def _module_of(model: type[DeclarativeBase]) -> str:
    """Return the `app.<package>` a model belongs to."""
    parts = model.__module__.split(".")
    return parts[1] if len(parts) > 1 else model.__module__


def _references(table: Table) -> str:
    """Which tables this one points at, once each, in declaration order."""
    seen: list[str] = []
    for column in table.columns:
        for key in column.foreign_keys:
            target = key.column.table.name
            if target != table.name and target not in seen:
                seen.append(target)
    return ", ".join(f"`{name}`" for name in seen)


def main() -> None:
    """Write the catalogue to `docs/TABLE_CATALOGUE.md`."""
    out: list[str] = []

    def print(*args: object) -> None:  # noqa: A001
        """Collect a line rather than writing it to a mangled console."""
        out.append(" ".join(str(arg) for arg in args))

    models = _models_by_table()
    by_module: dict[str, list[str]] = defaultdict(list)
    for name in sorted(Base.metadata.tables):
        model = models.get(name)
        by_module[_module_of(model) if model else "(unmapped)"].append(name)

    platform = set(_PLATFORM_TABLES)
    print(_PREAMBLE.format(total=len(Base.metadata.tables), platform=len(platform)))

    for module in sorted(by_module):
        print(f"\n### `app/{module}`\n")
        print("| Table | Store | Holds | Points at |")
        print("| --- | --- | --- | --- |")
        for name in by_module[module]:
            table = Base.metadata.tables[name]
            model = models.get(name)
            where = "platform" if name in platform else "firm store"
            soft = model is not None and issubclass(model, BaseEntity)
            holds = _summary(model) if model else ""
            if soft:
                where += " ¹"
            print(f"| `{name}` | {where} | {holds} | {_references(table)} |")

    print(_FOOTER)

    target = Path(__file__).resolve().parents[2] / "docs" / "TABLE_CATALOGUE.md"
    target.write_text("\n".join(out) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {target} ({len(Base.metadata.tables)} tables)\n")


_PREAMBLE = """# Table catalogue — every table, where it lives, what it holds

**{total} tables**, of which **{platform}** live only in the platform store.
Generated from the ORM metadata, not written by hand:

```powershell
uv run python scripts/dump_table_catalogue.py    # rewrites this file in place
```

Re-run it rather than editing the tables below. A hand-kept list of two hundred
rows is a list that rots, and `CLAUDE.md` carries the scars of several.

## The three stores, and why a table's home decides what a query can do

A firm's data lives in one of three arrangements, chosen when the firm is
created and never changed (see
[`TENANCY_AND_STORES.md`](TENANCY_AND_STORES.md)):

| Mode | Where the firm's tables are |
| --- | --- |
| `SHARED` | The shared database, schema `firm_shared`, alongside other shared firms |
| `SCHEMA` | Its own schema in the shared database |
| `DATABASE` | Its own database, possibly on another server |

**Two consequences run through every row below.**

*A platform table exists once.* `users`, `firms`, `user_firms` and the rest of
the platform list live **only** in the platform schema. A firm-owned service
that needs one opens the platform store deliberately, with `platform_reader()`
from `app/common/firm_metadata.py` -- a tenant session raises `UndefinedTable`
for them. `_PLATFORM_TABLES` in `app/core/tenancy/lifecycle.py` is the
authority on which they are, and "has no firm column" is **not** a test:
`geo_countries` has none and lives in every store.

*A firm table exists once per store.* Every firm-owned table is created in
`firm_shared` and in each dedicated schema or database, so the same table name
holds different rows in each. Nothing joins across them, which is why a
cross-firm view iterates stores rather than writing one query -- and why
`audit_logs` cannot answer "everything that happened" from one place.

## How to read the columns

- **Store** -- `platform` or `firm store`, as above.
- **Holds** -- the model's own docstring. Where it is blank, the model has no
  docstring; that is a gap in the code, not in this document.
- **Points at** -- the tables this one declares a foreign key to **in the
  ORM**. Read one line of it with care: nearly every firm-owned table points
  at `firms`, and `firms` lives only in the platform store. The column is
  real everywhere; the **constraint** is created only where the target table
  exists, because a migration declares such a reference only when
  `sa.inspect(op.get_bind()).has_table(...)` finds it (`_external_fk` in
  `20260809_0042`). So in `firm_shared` and in every dedicated store, `firm_id`
  is an unenforced reference by design -- the database cannot check it, and
  nothing may rely on it doing so.

¹ marks a table extending `BaseEntity`: UUID `id`, created/updated actor and
timestamp, `version` for optimistic concurrency, and `is_deleted` /
`deleted_at` soft delete. Repositories exclude soft-deleted rows unless asked.
`audit_logs` is the exception to everything -- append-only, enforced by a
trigger each schema owns its own copy of.
"""

_FOOTER = """
---

## What this catalogue cannot tell you

- **Which tables hold live rows.** 42 of them held none in any store when
  `docs/MODULE_STATUS.md` last asked, and asking that question found four
  defects in one day. Built is not the same as used.
- **What an action writes.** [`DATA_TRAIL_BY_OPERATION.md`](DATA_TRAIL_BY_OPERATION.md)
  answers that per operation, with a query to paste.
- **How the rows behave.** The module's section in
  [`FUNCTIONAL_GUIDE.md`](FUNCTIONAL_GUIDE.md) is the workflow;
  [`DATA_MODEL_IDENTITY_AND_FIRMS.md`](DATA_MODEL_IDENTITY_AND_FIRMS.md) and
  [`FIRM_DOMAIN_MODEL.md`](FIRM_DOMAIN_MODEL.md) are the two domains drawn as
  diagrams rather than listed.
"""


if __name__ == "__main__":
    main()
