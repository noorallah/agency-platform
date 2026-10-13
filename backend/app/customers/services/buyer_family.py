"""A parent buyer and the shops under it (backlog 125).

A chain is one company with many shops. Each shop is a customer of its own --
its own address, bills, dues and salesman -- and names the parent it sits
under. The GST number is typed once, on the parent: a shop that sends none
takes the parent's, and a shop in another state sends its own.

**The number a shop takes is copied onto the shop's row by the server**, and
marked ``gst_number_from_parent``. Some twenty readers decide tax, the place
of supply, GSTR-1 and the e-invoice from ``customers.gst_number``, several of
them in SQL; leaving a shop's column empty and resolving the parent on every
read would bill a registered buyer as unregistered at the first reader that
was missed. So the column always holds the number the shop is billed under,
the marker says whose it is, and ``UQ_customers_firm_gst_number_own_active``
holds a typed number to one live customer by leaving the copies out.

The link is one level deep: a shop has no shops, and a parent has no parent.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError
from app.customers.models import Customer
from app.customers.schemas.customer import CustomerFamily, CustomerFamilyMember

#: The fields of a write that can move the GST number a customer is billed
#: under. A save that names none of them leaves the family rules alone.
_FAMILY_FIELDS = ("parent_customer_id", "gst_number", "gst_registration_type")


@dataclass(frozen=True)
class FamilyFacts:
    """What a list row says about a customer's place in a family."""

    parent_code: str | None = None
    parent_name: str | None = None
    shop_count: int = 0


class BuyerFamily:
    """Answer and guard the parent-and-shops link on one session."""

    def __init__(self, session: Session) -> None:
        """Bind the rules to one request unit of work."""
        self._session = session

    def resolve(
        self,
        firm_id: UUID,
        *,
        customer: Customer | None,
        values: dict[str, object],
    ) -> dict[str, object]:
        """Return the GST columns a write must store, given its parent.

        ``values`` is what the write sends: everything on a create, only the
        fields named on an update. The answer is empty when the write touches
        neither the parent nor the number.

        A shop that sends no number, its parent's number, or the number it
        was shown (a form sends back what it read) takes the parent's. A
        customer taken out from under its parent gives the parent's number
        back rather than keeping a copy as its own.

        Raises:
            ValidationError: If the parent is not a customer that can have
                shops, or the customer cannot be a shop.
            ConflictError: If the number is held by another customer.

        """
        if customer is not None and not any(key in values for key in _FAMILY_FIELDS):
            return {}
        current_parent_id = customer.parent_customer_id if customer else None
        parent_id = values.get("parent_customer_id", current_parent_id)
        inherited = bool(customer is not None and customer.gst_number_from_parent)
        stored = customer.gst_number if customer is not None else None
        if "gst_number" in values:
            sent = _text(values["gst_number"])
        else:
            sent = None if inherited else stored
        echoed = inherited and sent == stored
        if isinstance(parent_id, UUID):
            parent = self._parent(
                firm_id, parent_id, customer=customer, current_id=current_parent_id
            )
            if sent is None or echoed or sent == parent.gst_number:
                return {
                    "gst_number": parent.gst_number,
                    "gst_registration_type": parent.gst_registration_type,
                    "gst_number_from_parent": True,
                }
            own: str | None = sent
        else:
            own = None if echoed else sent
        if own and (own != stored or inherited):
            self.assert_number_free(
                firm_id, own, excluding_id=customer.id if customer else None
            )
        return {"gst_number": own, "gst_number_from_parent": False}

    def assert_number_free(
        self,
        firm_id: UUID,
        gst_number: str,
        *,
        excluding_id: UUID | None,
        doing: str = "saved",
    ) -> None:
        """Refuse a GST number another live customer holds as its own.

        The partial unique index is the guard; this is the message, which
        names the holder and says what to do instead.
        """
        holder = self.number_holder(firm_id, gst_number, excluding_id=excluding_id)
        if holder is None:
            return
        raise ConflictError(
            f"This customer cannot be {doing}: GST number {gst_number} is "
            f"held by {holder.code} {holder.name}. A GST number is entered "
            f"once. Make this customer a shop of {holder.code} and leave its "
            "GST number blank; a shop takes its parent's."
        )

    def number_holder(
        self, firm_id: UUID, gst_number: str, *, excluding_id: UUID | None
    ) -> Customer | None:
        """Return the live customer a GST number was typed on, if any."""
        statement = select(Customer).where(
            Customer.firm_id == firm_id,
            Customer.is_deleted.is_(False),
            Customer.gst_number == gst_number,
            Customer.gst_number_from_parent.is_(False),
        )
        if excluding_id is not None:
            statement = statement.where(Customer.id != excluding_id)
        return self._session.scalars(statement.order_by(Customer.code)).first()

    def shops(
        self, parent_id: UUID, *, include_deleted: bool = False
    ) -> list[Customer]:
        """Return the shops under a parent, by code."""
        statement = select(Customer).where(Customer.parent_customer_id == parent_id)
        if not include_deleted:
            statement = statement.where(Customer.is_deleted.is_(False))
        return list(self._session.scalars(statement.order_by(Customer.code)))

    def assert_no_shops(self, customer: Customer, doing: str) -> None:
        """Refuse an action on a parent that would strand its shops.

        The foreign key is RESTRICT, but a soft delete never reaches it, so
        the refusal lives here.
        """
        shops = self.shops(customer.id)
        if not shops:
            return
        named = ", ".join(shop.code for shop in shops[:5])
        more = f" and {len(shops) - 5} more" if len(shops) > 5 else ""
        raise ConflictError(
            f"{customer.code} {customer.name} cannot {doing}: it is the "
            f"parent of {len(shops)} shop(s) ({named}{more}). Move them to "
            "another parent or take them out from under it first."
        )

    def assert_restorable(self, customer: Customer) -> None:
        """Refuse to restore into a family that has moved on.

        A delete released the customer's own GST number, and a deleted shop
        does not hold its parent in place.
        """
        if customer.parent_customer_id is not None:
            parent = self._session.get(Customer, customer.parent_customer_id)
            if parent is None or parent.is_deleted:
                raise ConflictError(
                    f"{customer.code} cannot be restored: its parent "
                    f"{parent.code if parent else ''} is deleted. Restore the "
                    "parent first."
                )
            if parent.parent_customer_id is not None:
                raise ConflictError(
                    f"{customer.code} cannot be restored: its parent "
                    f"{parent.code} is now a shop itself."
                )
            if customer.gst_number_from_parent:
                customer.gst_number = parent.gst_number
                customer.gst_registration_type = parent.gst_registration_type
                return
        if customer.gst_number:
            self.assert_number_free(
                customer.firm_id,
                customer.gst_number,
                excluding_id=customer.id,
                doing="restored",
            )

    def facts(self, rows: list[Customer]) -> dict[UUID, FamilyFacts]:
        """Return each row's parent name and shop count, read once for all."""
        if not rows:
            return {}
        parent_ids = {
            row.parent_customer_id for row in rows if row.parent_customer_id is not None
        }
        parents: dict[UUID, tuple[str, str]] = {}
        if parent_ids:
            parents = {
                parent_id: (code, name)
                for parent_id, code, name in self._session.execute(
                    select(Customer.id, Customer.code, Customer.name).where(
                        Customer.id.in_(parent_ids)
                    )
                ).all()
            }
        counts: dict[UUID, int] = {
            parent_id: int(count)
            for parent_id, count in self._session.execute(
                select(Customer.parent_customer_id, func.count(Customer.id))
                .where(
                    Customer.parent_customer_id.in_([row.id for row in rows]),
                    Customer.is_deleted.is_(False),
                )
                .group_by(Customer.parent_customer_id)
            ).all()
        }
        facts: dict[UUID, FamilyFacts] = {}
        for row in rows:
            code, name = (
                parents.get(row.parent_customer_id, (None, None))
                if row.parent_customer_id is not None
                else (None, None)
            )
            facts[row.id] = FamilyFacts(
                parent_code=code, parent_name=name, shop_count=counts.get(row.id, 0)
            )
        return facts

    def family(self, customer: Customer) -> CustomerFamily:
        """Return the parent and its shops, with what they owe together."""
        root = customer
        if customer.parent_customer_id is not None:
            root = self._session.get(Customer, customer.parent_customer_id) or customer
        rows = [root, *self.shops(root.id)]
        members = [
            CustomerFamilyMember(
                id=row.id,
                code=row.code,
                name=row.name,
                is_parent=row.id == root.id,
                gst_number=row.gst_number,
                gst_number_from_parent=row.gst_number_from_parent,
                status=row.status,
                place=_place(row),
                current_outstanding=row.current_outstanding,
                unapplied_advance_balance=row.unapplied_advance_balance,
            )
            for row in rows
        ]
        return CustomerFamily(
            parent_id=root.id,
            members=members,
            total_outstanding=sum(
                (row.current_outstanding for row in rows), Decimal("0")
            ),
            total_unapplied_advance=sum(
                (row.unapplied_advance_balance for row in rows), Decimal("0")
            ),
        )

    def _parent(
        self,
        firm_id: UUID,
        parent_id: UUID,
        *,
        customer: Customer | None,
        current_id: UUID | None,
    ) -> Customer:
        """Return the parent a write names, checked where the write moves it.

        A parent already on the row is read and not judged again, so an
        unrelated edit of a shop is never refused for something that
        happened to its parent since.
        """
        parent = self._session.get(Customer, parent_id)
        if parent is None or parent.firm_id != firm_id:
            raise ValidationError("The parent customer is not one of this firm's.")
        if parent_id == current_id:
            return parent
        if parent.is_deleted:
            raise ValidationError("The parent customer is not one of this firm's.")
        if customer is not None and parent.id == customer.id:
            raise ValidationError("A customer cannot be its own parent.")
        if parent.is_cash_sale:
            raise ValidationError(
                f"{parent.name} is the walk-in customer and cannot have shops."
            )
        if customer is not None and customer.is_cash_sale:
            raise ValidationError(
                f"{customer.name} is the walk-in customer and is nobody's shop."
            )
        if parent.parent_customer_id is not None:
            above = self._session.get(Customer, parent.parent_customer_id)
            named = above.code if above is not None else "its parent"
            raise ValidationError(
                f"{parent.code} {parent.name} is itself a shop of {named}. "
                f"Name {named} as the parent: shops sit one level under it."
            )
        if customer is not None:
            self.assert_no_shops(customer, "be made a shop")
        return parent


def _text(value: object) -> str | None:
    """Return a sent GST number as text, a blank one as none."""
    return str(value).strip() or None if value is not None else None


def _place(customer: Customer) -> str | None:
    """Return the area and city of a customer's billing address."""
    live = [row for row in customer.addresses if not row.is_deleted]
    if not live:
        return None
    chosen = next((row for row in live if row.is_default_billing), live[0])
    return ", ".join(part for part in (chosen.area, chosen.city) if part) or None


__all__ = ["BuyerFamily", "FamilyFacts"]
