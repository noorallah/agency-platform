"""A supplier company and the branches under it (backlog 127).

A supplier company is one main office with many branches. Each branch is a
supplier of its own -- its own GST number, address, bills and bank account --
and names the main office it sits under. An order placed on one office may
be received from another and billed by it, and a payment to the main office
may clear a branch's bills.

Nothing is copied between the offices. A branch is registered in its own
state, so its GST number is its own, and ``UQ_vendors_firm_gstin_active``
already holds a number to one live supplier.

The link is one level deep: a branch has no branches, and a main office has
no main office above it.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError
from app.vendors.models import Vendor


@dataclass(frozen=True)
class SupplierFamilyFacts:
    """What a list row says about a supplier's place in a company."""

    parent_code: str | None = None
    parent_name: str | None = None
    branch_count: int = 0


class SupplierFamily:
    """Answer and guard the main-office-and-branches link on one session."""

    def __init__(self, session: Session) -> None:
        """Bind the rules to one request unit of work."""
        self._session = session

    def assert_parent(
        self,
        firm_id: UUID,
        *,
        vendor: Vendor | None,
        parent_id: UUID | None,
    ) -> None:
        """Refuse a main office a write may not put a supplier under.

        A main office already on the row is not judged again, so an
        unrelated edit of a branch is never refused for something that
        happened to its main office since.

        Raises:
            ValidationError: If the main office is not one of the firm's
                suppliers, is the supplier itself or is a branch, or the
                supplier has branches of its own.

        """
        if parent_id is None:
            return
        if vendor is not None and vendor.parent_vendor_id == parent_id:
            return
        parent = self._session.get(Vendor, parent_id)
        if parent is None or parent.firm_id != firm_id or parent.is_deleted:
            raise ValidationError(
                "The main office is not one of this firm's suppliers."
            )
        if vendor is not None and parent.id == vendor.id:
            raise ValidationError("A supplier cannot be its own main office.")
        if parent.parent_vendor_id is not None:
            above = self._session.get(Vendor, parent.parent_vendor_id)
            named = above.code if above is not None else "its main office"
            raise ValidationError(
                f"{parent.code} {parent.name} is itself a branch of {named}. "
                f"Name {named} as the main office: branches sit one level "
                "under it."
            )
        if vendor is not None:
            self.assert_no_branches(vendor, "be made a branch")

    def branches(
        self, parent_id: UUID, *, include_deleted: bool = False
    ) -> list[Vendor]:
        """Return the branches under a main office, by code."""
        statement = select(Vendor).where(Vendor.parent_vendor_id == parent_id)
        if not include_deleted:
            statement = statement.where(Vendor.is_deleted.is_(False))
        return list(self._session.scalars(statement.order_by(Vendor.code)))

    def assert_no_branches(self, vendor: Vendor, doing: str) -> None:
        """Refuse an action on a main office that would strand its branches.

        The foreign key is RESTRICT, but a soft delete never reaches it, so
        the refusal lives here.
        """
        branches = self.branches(vendor.id)
        if not branches:
            return
        named = ", ".join(branch.code for branch in branches[:5])
        more = f" and {len(branches) - 5} more" if len(branches) > 5 else ""
        raise ConflictError(
            f"{vendor.code} {vendor.name} cannot {doing}: it is the main "
            f"office of {len(branches)} branch(es) ({named}{more}). Move them "
            "to another main office or take them out from under it first."
        )

    def assert_restorable(self, vendor: Vendor) -> None:
        """Refuse to restore a branch into a company that has moved on."""
        if vendor.parent_vendor_id is None:
            return
        parent = self._session.get(Vendor, vendor.parent_vendor_id)
        if parent is None or parent.is_deleted:
            raise ConflictError(
                f"{vendor.code} cannot be restored: its main office "
                f"{parent.code if parent else ''} is deleted. Restore the "
                "main office first."
            )
        if parent.parent_vendor_id is not None:
            raise ConflictError(
                f"{vendor.code} cannot be restored: its main office "
                f"{parent.code} is now a branch itself."
            )

    def facts(self, rows: list[Vendor]) -> dict[UUID, SupplierFamilyFacts]:
        """Return each row's main office and branch count, read once for all."""
        if not rows:
            return {}
        parent_ids = {
            row.parent_vendor_id for row in rows if row.parent_vendor_id is not None
        }
        parents: dict[UUID, tuple[str, str]] = {}
        if parent_ids:
            parents = {
                parent_id: (code, name)
                for parent_id, code, name in self._session.execute(
                    select(Vendor.id, Vendor.code, Vendor.name).where(
                        Vendor.id.in_(parent_ids)
                    )
                ).all()
            }
        counts: dict[UUID, int] = {
            parent_id: int(count)
            for parent_id, count in self._session.execute(
                select(Vendor.parent_vendor_id, func.count(Vendor.id))
                .where(
                    Vendor.parent_vendor_id.in_([row.id for row in rows]),
                    Vendor.is_deleted.is_(False),
                )
                .group_by(Vendor.parent_vendor_id)
            ).all()
        }
        facts: dict[UUID, SupplierFamilyFacts] = {}
        for row in rows:
            code, name = (
                parents.get(row.parent_vendor_id, (None, None))
                if row.parent_vendor_id is not None
                else (None, None)
            )
            facts[row.id] = SupplierFamilyFacts(
                parent_code=code, parent_name=name, branch_count=counts.get(row.id, 0)
            )
        return facts

    def members(self, vendor: Vendor) -> list[Vendor]:
        """Return the main office first, then its live branches by code."""
        root = vendor
        if vendor.parent_vendor_id is not None:
            root = self._session.get(Vendor, vendor.parent_vendor_id) or vendor
        return [root, *self.branches(root.id)]


def company_of(session: Session, vendor_ids: Iterable[UUID]) -> dict[UUID, UUID]:
    """Return the main office each supplier belongs to, itself where it has none.

    Two suppliers are offices of one company exactly when they answer the
    same id here. One read, whatever the number asked about.
    """
    wanted = set(vendor_ids)
    if not wanted:
        return {}
    return {
        vendor_id: parent_id or vendor_id
        for vendor_id, parent_id in session.execute(
            select(Vendor.id, Vendor.parent_vendor_id).where(Vendor.id.in_(wanted))
        )
    }


def same_company(session: Session, first: UUID, second: UUID) -> bool:
    """Say whether two suppliers are the same one or offices of one company."""
    if first == second:
        return True
    roots = company_of(session, (first, second))
    return first in roots and second in roots and roots[first] == roots[second]


def assert_office_of(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID,
    of_vendor_id: UUID,
    document: str,
    against: str,
) -> None:
    """Refuse a document in the name of a supplier outside the company.

    ``document`` is what is being written ("goods receipt") and ``against``
    what it continues ("the order"). The supplier may be the one that names,
    its main office, or another branch of the same main office.

    Raises:
        ValidationError: If the supplier is not this firm's, is deleted, or
            is no office of the company the earlier document names.

    """
    if vendor_id == of_vendor_id:
        return
    vendor = session.get(Vendor, vendor_id)
    if vendor is None or vendor.firm_id != firm_id or vendor.is_deleted:
        raise ValidationError("The supplier is not one of this firm's.")
    if same_company(session, vendor_id, of_vendor_id):
        return
    other = session.get(Vendor, of_vendor_id)
    named = f"{other.code} {other.name}" if other is not None else "another supplier"
    raise ValidationError(
        f"This {document} is from {vendor.code} {vendor.name}, but {against} "
        f"is on {named}. A {document} is from the supplier {against} names, "
        "its main office or one of its branches."
    )


__all__ = [
    "SupplierFamily",
    "SupplierFamilyFacts",
    "assert_office_of",
    "company_of",
    "same_company",
]
