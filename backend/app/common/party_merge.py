"""Duplicate check and merge of customers and suppliers (MST-3, decision A136).

A firm that has been trading a while has a second "Sri Balaji Stores" --
typed again by someone who did not find the first. This module warns before
the second is saved, and merges two that already exist:

* **The check** is a warning, never a refusal: the same GSTIN, the same
  phone (last ten digits), or the same name once punctuation and the words
  every shop name carries (stores, traders, enterprises, pvt, ltd...) are
  set aside.
* **The merge** keeps one record (the survivor) and folds the other into it
  in one transaction. Every column that names the duplicate is re-pointed --
  found from the schema's foreign keys, plus the few columns that name a
  party without one -- so a table added next year is merged without anyone
  remembering it. Where a unique key would collide (both have a value for
  one custom field, both are on one beat), the survivor's row stands; for
  the per-period ledgers the amounts are added together. A customer's stored
  balances are summed. The duplicate is soft-deleted and records which
  record it was merged into.
* A merge is refused when the duplicate has an invoice or a settlement dated
  in a locked financial year: the books of a closed year are not reopened by
  a change of party.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    Column,
    Numeric,
    Table,
    UniqueConstraint,
    and_,
    delete,
    select,
    update,
)
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now

#: Words a trade name carries that say nothing about which business it is.
_NOISE = frozenset(
    {
        "stores",
        "store",
        "traders",
        "trader",
        "trading",
        "enterprises",
        "enterprise",
        "agencies",
        "agency",
        "and",
        "co",
        "company",
        "pvt",
        "private",
        "ltd",
        "limited",
        "llp",
        "m/s",
        "ms",
        "sons",
        "brothers",
        "bros",
        "the",
    }
)


def name_key(name: str | None) -> str:
    """Return a name reduced to what tells one business from another."""
    text = re.sub(r"\bm\s*/\s*s\b\.?", " ", (name or "").lower())
    words = re.sub(r"[^a-z0-9 ]+", " ", text).split()
    kept = [word for word in words if word not in _NOISE]
    return " ".join(kept or words)


def phone_key(phone: str | None) -> str:
    """Return a phone's last ten digits, or an empty string."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else ""


class DuplicateCandidate(BaseModel):
    """A record that may be the same party, and why."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    name: str
    reasons: list[str]


class PartyMergeWrite(BaseModel):
    """Fold one record into the one the request is addressed to."""

    model_config = ConfigDict(extra="forbid")

    duplicate_id: UUID
    reason: str = Field(min_length=1, max_length=1000)


class PartyMergeResult(BaseModel):
    """What a merge moved."""

    model_config = ConfigDict(extra="forbid")

    survivor_id: UUID
    duplicate_id: UUID
    rows_moved: int
    rows_kept_from_survivor: int
    tables: list[str]


@dataclass(frozen=True)
class _Kind:
    """One kind of party that can be merged."""

    label: str
    table: str
    model_path: str
    gstin_field: str
    phone_fields: tuple[str, ...]
    #: Columns that name this party without a foreign key.
    bare_column: str
    #: Stored balances summed into the survivor.
    balances: tuple[str, ...]
    #: (table, party column, date column) checked against locked years.
    dated: tuple[tuple[str, str, str], ...]


KINDS: dict[str, _Kind] = {
    "CUSTOMER": _Kind(
        "customer",
        "customers",
        "app.customers.models:Customer",
        "gst_number",
        ("phone", "alternate_phone"),
        "customer_id",
        ("opening_balance", "current_outstanding", "unapplied_advance_balance"),
        (
            ("sales_invoices", "customer_id", "invoice_date"),
            ("settlements", "customer_id", "settlement_date"),
        ),
    ),
    "VENDOR": _Kind(
        "supplier",
        "vendors",
        "app.vendors.models:Vendor",
        "gstin",
        ("phone", "mobile"),
        "vendor_id",
        (),
        (
            ("purchase_invoices", "vendor_id", "invoice_date"),
            ("settlements", "vendor_id", "settlement_date"),
        ),
    ),
}


def _model(kind: _Kind) -> Any:  # noqa: ANN401 -- customer or supplier
    """Import a party model by its dotted path."""
    import importlib

    module, name = kind.model_path.split(":")
    return getattr(importlib.import_module(module), name)


def references(kind: _Kind) -> list[tuple[Table, Column[object]]]:
    """Return every column that names a party of this kind, from the schema."""
    found: list[tuple[Table, Column[object]]] = []
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            pointed = any(
                fk.column.table.name == kind.table for fk in column.foreign_keys
            )
            bare = column.name == kind.bare_column and not column.foreign_keys
            if pointed or bare:
                found.append((table, column))
    return found


def _unique_keys(table: Table, column: Column[object]) -> list[list[str]]:
    """Return the unique keys of a table that include a column."""
    keys = [
        [c.name for c in constraint.columns]
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
        and column.name in [c.name for c in constraint.columns]
    ]
    keys += [
        [c.name for c in index.columns]
        for index in table.indexes
        if index.unique and column.name in [c.name for c in index.columns]
    ]
    return keys


class PartyMergeService:
    """Find likely duplicates, and merge one party into another."""

    def __init__(self, session: Session) -> None:
        """Bind to the caller's session."""
        self._session = session

    def duplicates(
        self,
        kind_code: str,
        *,
        firm_id: UUID,
        name: str | None = None,
        phone: str | None = None,
        gstin: str | None = None,
        excluding: UUID | None = None,
    ) -> list[DuplicateCandidate]:
        """Return the firm's live parties that look like the one described."""
        kind = KINDS[kind_code]
        model = _model(kind)
        wanted_name = name_key(name)
        wanted_phone = phone_key(phone)
        wanted_gstin = (gstin or "").strip().upper()
        if not (wanted_name or wanted_phone or wanted_gstin):
            return []
        answer: list[DuplicateCandidate] = []
        for row in self._session.scalars(
            select(model).where(
                model.firm_id == firm_id,
                model.is_deleted.is_(False),
            )
        ).all():
            if excluding is not None and row.id == excluding:
                continue
            reasons: list[str] = []
            theirs = (getattr(row, kind.gstin_field, None) or "").strip().upper()
            if wanted_gstin and theirs == wanted_gstin:
                reasons.append("same GSTIN")
            phones = {
                phone_key(getattr(row, field, None)) for field in kind.phone_fields
            } - {""}
            if wanted_phone and wanted_phone in phones:
                reasons.append("same phone")
            if wanted_name and name_key(row.name) == wanted_name:
                reasons.append("same name")
            if reasons:
                answer.append(
                    DuplicateCandidate(
                        id=row.id, code=row.code, name=row.name, reasons=reasons
                    )
                )
        return answer

    def merge(
        self,
        kind_code: str,
        survivor_id: UUID,
        data: PartyMergeWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PartyMergeResult:
        """Fold the duplicate into the survivor; commit once.

        Raises:
            ValidationError: If the two are one record, or the duplicate has
                a document in a locked financial year.

        """
        kind = KINDS[kind_code]
        model = _model(kind)
        if survivor_id == data.duplicate_id:
            raise ValidationError(f"A {kind.label} cannot be merged into itself.")
        survivor = self._party(model, survivor_id, firm_id, kind)
        duplicate = self._party(model, data.duplicate_id, firm_id, kind)
        self._refuse_locked(kind, duplicate.id, firm_id)

        moved = kept = 0
        touched: list[str] = []
        for table, column in references(kind):
            kept += self._settle_collisions(table, column, survivor.id, duplicate.id)
            result = self._session.execute(
                update(table)
                .where(column == duplicate.id)
                .values({column.name: survivor.id})
            )
            count = int(getattr(result, "rowcount", 0) or 0)
            if count:
                moved += count
                touched.append(f"{table.name}.{column.name}")
        # The re-pointing ran in SQL, past the session's loaded rows: read the
        # two parties again so what is summed is what the store holds.
        self._session.expire_all()
        survivor = self._party(model, survivor_id, firm_id, kind)
        duplicate = self._party(model, data.duplicate_id, firm_id, kind)
        for field in kind.balances:
            setattr(
                survivor,
                field,
                Decimal(str(getattr(survivor, field) or 0))
                + Decimal(str(getattr(duplicate, field) or 0)),
            )
            setattr(duplicate, field, Decimal("0"))
        now = utc_now()
        duplicate.is_deleted = True
        duplicate.deleted_at = now
        duplicate.deleted_by = actor_id
        duplicate.merged_into_id = survivor.id
        duplicate.updated_by = actor_id
        survivor.updated_by = actor_id
        record_audit(
            self._session,
            action=f"{kind.label}.merged",
            entity_type=kind.label,
            entity_id=survivor.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"duplicate_id": str(duplicate.id), "code": duplicate.code},
            after_data={
                "reason": data.reason.strip(),
                "rows_moved": moved,
                "rows_kept_from_survivor": kept,
                "tables": touched,
            },
        )
        self._session.commit()
        return PartyMergeResult(
            survivor_id=survivor.id,
            duplicate_id=duplicate.id,
            rows_moved=moved,
            rows_kept_from_survivor=kept,
            tables=touched,
        )

    # ---- helpers -------------------------------------------------------

    def _party(
        self,
        model: Any,  # noqa: ANN401 -- the customer or supplier model
        party_id: UUID,
        firm_id: UUID,
        kind: _Kind,
    ) -> Any:  # noqa: ANN401
        """Return one of the firm's live parties."""
        row = self._session.get(model, party_id)
        if (
            row is None
            or getattr(row, "is_deleted", False)
            or getattr(row, "firm_id", None) != firm_id
        ):
            raise ResourceNotFoundError(f"{kind.label.title()} not found.")
        return row

    def _refuse_locked(self, kind: _Kind, duplicate_id: UUID, firm_id: UUID) -> None:
        """Refuse when the duplicate has a document in a locked year."""
        from app.finance.models import FinancialYear

        locked = list(
            self._session.execute(
                select(FinancialYear.starts_on, FinancialYear.ends_on).where(
                    FinancialYear.firm_id == firm_id,
                    FinancialYear.is_deleted.is_(False),
                    FinancialYear.is_locked.is_(True),
                )
            ).all()
        )
        if not locked:
            return
        for table_name, party_column, date_column in kind.dated:
            table = Base.metadata.tables.get(table_name)
            if table is None:
                continue
            for starts_on, ends_on in locked:
                hit = self._session.execute(
                    select(table.c.id)
                    .where(
                        table.c[party_column] == duplicate_id,
                        table.c[date_column] >= starts_on,
                        table.c[date_column] <= ends_on,
                    )
                    .limit(1)
                ).first()
                if hit is not None:
                    raise ValidationError(
                        f"This {kind.label} has documents in a locked financial "
                        f"year ({starts_on:%d-%m-%Y} to {ends_on:%d-%m-%Y}); a "
                        "closed year's books are not changed by a merge."
                    )

    def _settle_collisions(
        self, table: Table, column: Column[object], survivor: UUID, duplicate: UUID
    ) -> int:
        """Clear the duplicate's rows a unique key would refuse; return how many.

        The survivor's row stands; on a per-period ledger the duplicate's
        amounts are added to it first.
        """
        cleared = 0
        for key in _unique_keys(table, column):
            others = [name for name in key if name != column.name]
            mine = table.alias("mine")
            theirs = table.alias("theirs")
            match = [theirs.c[column.name] == survivor] + [
                theirs.c[name] == mine.c[name] for name in others
            ]
            if "is_deleted" in table.c:
                match.append(theirs.c.is_deleted.is_(False))
            clashing = list(
                self._session.execute(
                    select(mine.c.id, theirs.c.id)
                    .select_from(mine.join(theirs, and_(*match)))
                    .where(mine.c[column.name] == duplicate)
                ).all()
            )
            if not clashing:
                continue
            numeric = [
                c.name
                for c in table.columns
                if isinstance(c.type, Numeric) and table.name.endswith("_ledgers")
            ]
            for mine_id, theirs_id in clashing:
                if numeric:
                    values = self._session.execute(
                        select(*[table.c[name] for name in numeric]).where(
                            table.c.id == mine_id
                        )
                    ).one()
                    self._session.execute(
                        update(table)
                        .where(table.c.id == theirs_id)
                        .values(
                            {
                                name: table.c[name] + (value or 0)
                                for name, value in zip(numeric, values, strict=True)
                            }
                        )
                    )
                self._session.execute(delete(table).where(table.c.id == mine_id))
                cleared += 1
        return cleared
