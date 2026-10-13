"""A supplier company and the branches under it (backlog 127).

A supplier company is one main office with many branches. Each branch is a
supplier of its own -- its own GST number, address, bills and bank account --
and names the main office it sits under. An order placed on one office may
be received from another and billed by it, and a payment to the main office
may clear a branch's bills.

**A GST number is typed once** (backlog 136), as on the buyer side
(``app/customers/services/buyer_family.py``). A branch in another state types
its own. A branch that sends none takes its main office's: the server copies
the number onto the branch's row and marks it ``gstin_from_parent``, because
the tax on a purchase, the GSTR-2B match and the credit checks all read
``vendors.gstin``, several of them in SQL, and a branch left blank would be
taxed as an unregistered supplier at the first reader that did not look up
its main office. ``UQ_vendors_firm_gstin_own_active`` holds a typed number
to one live supplier by leaving the copies out.

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

#: The fields of a write that can move the GST number a supplier is taxed
#: under. A save that names none of them leaves the family rules alone.
FAMILY_FIELDS = ("parent_vendor_id", "gstin", "gst_registration_type")


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

    def resolve(
        self,
        firm_id: UUID,
        *,
        vendor: Vendor | None,
        values: dict[str, object],
    ) -> dict[str, object]:
        """Return the GST columns a write must store, given its main office.

        ``values`` is what the write sends: everything on a create, only the
        fields named on an update. The answer is empty when the write touches
        neither the main office nor the number.

        A branch that sends no number, its main office's number, or the
        number it was shown (a form sends back what it read) takes the main
        office's. A supplier taken out from under its main office gives the
        number back rather than keeping a copy as its own.

        Raises:
            ValidationError: If the main office is not a supplier that can
                have branches, or the supplier cannot be a branch.
            ConflictError: If the number is held by another supplier.

        """
        if vendor is not None and not any(key in values for key in FAMILY_FIELDS):
            return {}
        current_parent_id = vendor.parent_vendor_id if vendor else None
        parent_id = values.get("parent_vendor_id", current_parent_id)
        inherited = bool(vendor is not None and vendor.gstin_from_parent)
        stored = vendor.gstin if vendor is not None else None
        if "gstin" in values:
            sent = _text(values["gstin"])
        else:
            sent = None if inherited else stored
        echoed = inherited and sent == stored
        if isinstance(parent_id, UUID):
            self.assert_parent(firm_id, vendor=vendor, parent_id=parent_id)
            parent = self._session.get(Vendor, parent_id)
            if parent is not None and (sent is None or echoed or sent == parent.gstin):
                return {
                    "gstin": parent.gstin,
                    "gst_registration": parent.gst_registration,
                    "gst_registration_type": parent.gst_registration_type,
                    "gstin_from_parent": True,
                }
            own: str | None = sent
        else:
            own = None if echoed else sent
        if own and (own != stored or inherited):
            self.assert_number_free(
                firm_id, own, excluding_id=vendor.id if vendor else None
            )
        answer: dict[str, object] = {"gstin": own, "gstin_from_parent": False}
        if inherited and "gst_registration_type" not in values:
            # The type came with the number, and goes back with it.
            answer["gst_registration_type"] = None
            if own is None and "gst_registration" not in values:
                answer["gst_registration"] = False
        return answer

    def assert_number_free(
        self,
        firm_id: UUID,
        gstin: str,
        *,
        excluding_id: UUID | None,
        doing: str = "saved",
    ) -> None:
        """Refuse a GST number another live supplier holds as its own.

        The partial unique index is the guard; this is the message, which
        names the holder and says what to do instead.
        """
        holder = self.number_holder(firm_id, gstin, excluding_id=excluding_id)
        if holder is None:
            return
        raise ConflictError(
            f"This supplier cannot be {doing}: GST number {gstin} is held by "
            f"{holder.code} {holder.name}. A GST number is entered once. Make "
            f"this supplier a branch of {holder.code} and leave its GST "
            "number blank; a branch takes its main office's."
        )

    def number_holder(
        self, firm_id: UUID, gstin: str, *, excluding_id: UUID | None
    ) -> Vendor | None:
        """Return the live supplier a GST number was typed on, if any."""
        statement = select(Vendor).where(
            Vendor.firm_id == firm_id,
            Vendor.is_deleted.is_(False),
            Vendor.gstin == gstin,
            Vendor.gstin_from_parent.is_(False),
        )
        if excluding_id is not None:
            statement = statement.where(Vendor.id != excluding_id)
        return self._session.scalars(statement.order_by(Vendor.code)).first()

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
        """Refuse to restore into a company, or a number, that has moved on.

        A delete released the supplier's own GST number, and a deleted
        branch does not hold its main office in place.
        """
        if vendor.parent_vendor_id is not None:
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
            if vendor.gstin_from_parent:
                vendor.gstin = parent.gstin
                vendor.gst_registration = parent.gst_registration
                vendor.gst_registration_type = parent.gst_registration_type
                return
        if vendor.gstin:
            self.assert_number_free(
                vendor.firm_id, vendor.gstin, excluding_id=vendor.id, doing="restored"
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


def _text(value: object) -> str | None:
    """Return a sent GST number as text, a blank one as none."""
    return str(value).strip() or None if value is not None else None


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
    "FAMILY_FIELDS",
    "SupplierFamily",
    "SupplierFamilyFacts",
    "assert_office_of",
    "company_of",
    "same_company",
]
