"""Which GSTIN a document is supplied under (STK-2, decision A127).

A firm registered in two states holds two GSTINs -- one per state, as GST
requires (CGST Act section 25(1)) -- and each branch supplies under the one of
the state it is in. A branch that carries a GSTIN of its own supplies under
it; every other branch supplies under the firm's. This module is the one
place that answers the question, so a print, a return, an e-invoice and a
transfer cannot each decide it differently.

A return is filed **per GSTIN**, so it reads only the documents of the
branches that supply under that GSTIN. A firm with one GSTIN is not scoped at
all, which keeps every return exactly what it was before branches had GSTINs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.branches.models import Branch
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError


def _clean(value: str | None) -> str | None:
    """Return a GSTIN in capitals without spaces, or None for a blank."""
    text = "".join((value or "").split()).upper()
    return text or None


@dataclass(frozen=True)
class GstRegistration:
    """One GSTIN the firm files under, and the branches that supply under it."""

    gstin: str
    state_code: str
    #: True for the firm's own GSTIN, which also covers every branch without
    #: one of its own.
    is_firm: bool
    branch_ids: frozenset[UUID] = field(default_factory=frozenset)
    branch_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class GstinScope:
    """The documents a return for one GSTIN reads.

    ``branch_ids`` is None when the firm has only one GSTIN: nothing is
    filtered. Otherwise a document counts when its branch is in the set, and
    for the firm's own GSTIN also when it names no branch at all.
    """

    gstin: str
    branch_ids: frozenset[UUID] | None = None
    includes_unbranched: bool = True

    def applies(
        self, column: ColumnElement[UUID] | InstrumentedAttribute[UUID]
    ) -> ColumnElement[bool]:
        """Return the condition a document's ``branch_id`` must meet."""
        if self.branch_ids is None:
            return true()
        inside = column.in_(list(self.branch_ids) or [None])
        return or_(inside, column.is_(None)) if self.includes_unbranched else inside


class BranchRegistration:
    """Answer which GSTIN a branch supplies under."""

    def __init__(self, session: Session) -> None:
        """Bind to the caller's session."""
        self._session = session
        self._firms = FirmMetadataReader(session)

    def firm_gstin(self, firm_id: UUID) -> str | None:
        """Return the firm's own GSTIN."""
        return _clean(self._firms.get(firm_id).gst_number)

    def own_gstin(self, branch_id: UUID | None) -> str | None:
        """Return the branch's own GSTIN, or None where it has none."""
        if branch_id is None:
            return None
        branch = self._session.get(Branch, branch_id)
        if branch is None or branch.is_deleted:
            return None
        return _clean(branch.gstin)

    def gstin_for(self, firm_id: UUID, branch_id: UUID | None) -> str | None:
        """Return the GSTIN a document raised at ``branch_id`` is supplied under."""
        return self.own_gstin(branch_id) or self.firm_gstin(firm_id)

    def registrations(self, firm_id: UUID) -> list[GstRegistration]:
        """Return every GSTIN the firm files under, the firm's first."""
        firm = self.firm_gstin(firm_id)
        branches = self._session.execute(
            select(Branch.id, Branch.name, Branch.gstin).where(
                Branch.firm_id == firm_id, Branch.is_deleted.is_(False)
            )
        ).all()
        grouped: dict[str, tuple[set[UUID], list[str]]] = {}
        for branch_id, name, own in branches:
            gstin = _clean(own) or firm
            if gstin is None:
                continue
            ids, names = grouped.setdefault(gstin, (set(), []))
            ids.add(branch_id)
            names.append(name)
        if firm is not None:
            grouped.setdefault(firm, (set(), []))
        ordered = sorted(grouped, key=lambda gstin: (gstin != firm, gstin))
        return [
            GstRegistration(
                gstin=gstin,
                state_code=gstin[:2],
                is_firm=gstin == firm,
                branch_ids=frozenset(grouped[gstin][0]),
                branch_names=tuple(sorted(grouped[gstin][1])),
            )
            for gstin in ordered
        ]

    def scope(self, firm_id: UUID, gstin: str | None) -> GstinScope:
        """Return what a return filed under ``gstin`` reads.

        None asks for the firm's own GSTIN, which is what a return was before
        branches had GSTINs.

        Raises:
            ValidationError: If the firm has no GSTIN to file under, or
                ``gstin`` is not one of the firm's.

        """
        registrations = self.registrations(firm_id)
        wanted = _clean(gstin) or self.firm_gstin(firm_id)
        if wanted is None:
            raise ValidationError(
                "This firm has no GST number, so it has no return to file."
            )
        chosen = next((r for r in registrations if r.gstin == wanted), None)
        if chosen is None:
            raise ValidationError(f"{wanted} is not one of this firm's GSTINs.")
        if len(registrations) <= 1:
            return GstinScope(gstin=wanted)
        return GstinScope(
            gstin=wanted,
            branch_ids=chosen.branch_ids,
            includes_unbranched=chosen.is_firm,
        )
