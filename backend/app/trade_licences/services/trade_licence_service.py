"""Keep the licence register and say where each licence stands (backlog 54)."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.branches.models import Branch
from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.products.models import Product, ProductCategory
from app.trade_licences.models import TradeLicence, TradeLicenceType
from app.trade_licences.schemas import (
    LicenceHolderType,
    LicenceStanding,
    TradeLicenceResponse,
    TradeLicenceTypeWrite,
    TradeLicenceWrite,
)
from app.vendors.models import Vendor

#: How far ahead a licence counts as running out: the Home alert's window.
EXPIRY_WARNING_DAYS = 30

#: The types every firm starts with: (code, name, forms, expires). The first
#: go-live firms span pharma, food, agri and electronics, so all of them are
#: seeded rather than chosen by business profile; a firm deactivates what it
#: does not trade in. `OTHER` holds the old free-text numbers the register's
#: migration copies in, whose type nobody recorded.
DEFAULT_TYPES: tuple[tuple[str, str, str | None, bool], ...] = (
    ("DRUG_WHOLESALE", "Drug licence, wholesale", "20B / 21B", True),
    ("DRUG_RETAIL", "Drug licence, retail", "20 / 21", True),
    ("DRUG_SCHEDULE_X", "Drug licence, Schedule X", "20C / 21C", True),
    ("FSSAI", "FSSAI licence or registration", None, True),
    ("INSECTICIDE", "Insecticide licence", None, True),
    ("FERTILISER", "Fertiliser authorisation", None, True),
    ("SEED", "Seed licence", None, True),
    ("OTHER", "Other licence", None, False),
)


def standing_of(
    licence: TradeLicence, licence_type: TradeLicenceType, *, on: date
) -> tuple[LicenceStanding, int | None]:
    """Return where a licence stands on a day, and days until it runs out."""
    if licence.valid_from is not None and on < licence.valid_from:
        days = None if licence.valid_to is None else (licence.valid_to - on).days
        return LicenceStanding.NOT_YET_VALID, days
    if licence.valid_to is None:
        if licence_type.expires:
            return LicenceStanding.NO_EXPIRY_RECORDED, None
        return LicenceStanding.VALID, None
    days = (licence.valid_to - on).days
    if days < 0:
        return LicenceStanding.EXPIRED, days
    if days <= EXPIRY_WARNING_DAYS:
        return LicenceStanding.EXPIRING, days
    return LicenceStanding.VALID, days


def _snapshot(row: TradeLicence) -> dict[str, object]:
    """Describe a licence for the audit trail."""
    return {
        "licence_type_id": str(row.licence_type_id),
        "holder_type": row.holder_type,
        "branch_id": str(row.branch_id) if row.branch_id else None,
        "customer_id": str(row.customer_id) if row.customer_id else None,
        "vendor_id": str(row.vendor_id) if row.vendor_id else None,
        "licence_number": row.licence_number,
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
    }


class TradeLicenceService:
    """Types, the register, and where each licence stands."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    # -- types ---------------------------------------------------------------

    def ensure_default_types(self, firm_id: UUID, actor_id: UUID | None) -> None:
        """Seed the usual types a firm lacks, only where missing; flush only."""
        held = set(
            self._session.scalars(
                select(TradeLicenceType.code).where(
                    TradeLicenceType.firm_id == firm_id,
                    TradeLicenceType.is_deleted.is_(False),
                )
            ).all()
        )
        for code, name, forms, expires in DEFAULT_TYPES:
            if code in held:
                continue
            self._session.add(
                TradeLicenceType(
                    firm_id=firm_id,
                    code=code,
                    name=name,
                    form_numbers=forms,
                    expires=expires,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    def list_types(self, firm_id: UUID, actor_id: UUID) -> list[TradeLicenceType]:
        """Return the firm's types, seeding the usual ones on first read."""
        before = self._session.scalar(
            select(func.count(TradeLicenceType.id)).where(
                TradeLicenceType.firm_id == firm_id,
                TradeLicenceType.is_deleted.is_(False),
            )
        )
        if not before:
            self.ensure_default_types(firm_id, actor_id)
            self._session.commit()
        return list(
            self._session.scalars(
                select(TradeLicenceType)
                .where(
                    TradeLicenceType.firm_id == firm_id,
                    TradeLicenceType.is_deleted.is_(False),
                )
                .order_by(TradeLicenceType.code)
            ).all()
        )

    def get_type(self, type_id: UUID, *, firm_id: UUID) -> TradeLicenceType:
        """Return one live type of this firm, or refuse by name."""
        row = self._session.scalar(
            select(TradeLicenceType).where(
                TradeLicenceType.id == type_id,
                TradeLicenceType.firm_id == firm_id,
                TradeLicenceType.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Licence type not found.")
        return row

    def _assert_code_free(
        self, firm_id: UUID, code: str, excluding: UUID | None = None
    ) -> None:
        """Refuse a second live type with the same code."""
        query = select(TradeLicenceType.id).where(
            TradeLicenceType.firm_id == firm_id,
            TradeLicenceType.code == code,
            TradeLicenceType.is_deleted.is_(False),
        )
        if excluding is not None:
            query = query.where(TradeLicenceType.id != excluding)
        if self._session.scalar(query) is not None:
            raise ConflictError(f"A licence type with code {code} already exists.")

    def create_type(
        self, data: TradeLicenceTypeWrite, *, firm_id: UUID, actor_id: UUID
    ) -> TradeLicenceType:
        """Add one type."""
        self._assert_code_free(firm_id, data.code)
        row = TradeLicenceType(
            firm_id=firm_id, **data.model_dump(), created_by=actor_id
        )
        row.updated_by = actor_id
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="trade_licence_type.created",
            entity_type="trade_licence_type",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "name": row.name},
        )
        self._session.commit()
        return row

    def update_type(
        self,
        type_id: UUID,
        data: TradeLicenceTypeWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> TradeLicenceType:
        """Replace one type's fields."""
        row = self.get_type(type_id, firm_id=firm_id)
        self._assert_code_free(firm_id, data.code, excluding=row.id)
        before = {"code": row.code, "name": row.name, "expires": row.expires}
        for field, value in data.model_dump().items():
            setattr(row, field, value)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="trade_licence_type.updated",
            entity_type="trade_licence_type",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data={"code": row.code, "name": row.name, "expires": row.expires},
        )
        self._session.commit()
        return row

    def delete_type(self, type_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Delete a type no licence names; one in use is deactivated instead."""
        row = self.get_type(type_id, firm_id=firm_id)
        in_use = self._session.scalar(
            select(func.count(TradeLicence.id)).where(
                TradeLicence.licence_type_id == row.id,
                TradeLicence.is_deleted.is_(False),
            )
        )
        if in_use:
            raise ConflictError(
                f"{row.name} is on {in_use} licence(s). Deactivate it instead: "
                "the licences it names are the record of past trade."
            )
        # A soft delete never reaches the foreign key, so the goods that name
        # the type are counted here (backlog 54).
        needed_by = (
            self._session.scalar(
                select(func.count(Product.id)).where(
                    Product.required_licence_type_id == row.id,
                    Product.is_deleted.is_(False),
                )
            )
            or 0
        ) + (
            self._session.scalar(
                select(func.count(ProductCategory.id)).where(
                    ProductCategory.required_licence_type_id == row.id,
                    ProductCategory.is_deleted.is_(False),
                )
            )
            or 0
        )
        if needed_by:
            raise ConflictError(
                f"{needed_by} product(s) or categories need a {row.name}. "
                "Change what they need first, or deactivate the type."
            )
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="trade_licence_type.deleted",
            entity_type="trade_licence_type",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"code": row.code},
        )
        self._session.commit()

    # -- the register ----------------------------------------------------------

    def get_licence(self, licence_id: UUID, *, firm_id: UUID) -> TradeLicence:
        """Return one live licence of this firm, or refuse by name."""
        row = self._session.scalar(
            select(TradeLicence).where(
                TradeLicence.id == licence_id,
                TradeLicence.firm_id == firm_id,
                TradeLicence.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Licence not found.")
        return row

    def _assert_holder(self, data: TradeLicenceWrite, firm_id: UUID) -> None:
        """Refuse a holder that is not this firm's own live record."""
        checks: list[tuple[type[Branch] | type[Customer] | type[Vendor], UUID, str]]
        checks = []
        if data.branch_id is not None:
            checks.append((Branch, data.branch_id, "Branch"))
        if data.customer_id is not None:
            checks.append((Customer, data.customer_id, "Customer"))
        if data.vendor_id is not None:
            checks.append((Vendor, data.vendor_id, "Vendor"))
        for model, row_id, label in checks:
            found = self._session.scalar(
                select(model.id).where(
                    model.id == row_id,
                    model.firm_id == firm_id,
                    model.is_deleted.is_(False),
                )
            )
            if found is None:
                raise ValidationError(f"{label} not found in this firm.")

    def _checked(self, data: TradeLicenceWrite, firm_id: UUID) -> TradeLicenceType:
        """Validate a write against the firm's records; return its type."""
        licence_type = self.get_type(data.licence_type_id, firm_id=firm_id)
        self._assert_holder(data, firm_id)
        if licence_type.expires and data.valid_to is None:
            raise ValidationError(
                f"A {licence_type.name} runs out: enter its valid-to date, so "
                "the firm is warned before it does."
            )
        return licence_type

    def create_licence(
        self, data: TradeLicenceWrite, *, firm_id: UUID, actor_id: UUID
    ) -> TradeLicence:
        """Record one licence."""
        self._checked(data, firm_id)
        row = TradeLicence(
            firm_id=firm_id,
            **data.model_dump(mode="python"),
            created_by=actor_id,
            updated_by=actor_id,
        )
        row.holder_type = data.holder_type.value
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="trade_licence.created",
            entity_type="trade_licence",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=_snapshot(row),
        )
        self._session.commit()
        return row

    def update_licence(
        self,
        licence_id: UUID,
        data: TradeLicenceWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> TradeLicence:
        """Replace one licence's fields -- a renewal, or a correction."""
        row = self.get_licence(licence_id, firm_id=firm_id)
        self._checked(data, firm_id)
        before = _snapshot(row)
        for field, value in data.model_dump(mode="python").items():
            setattr(row, field, value)
        row.holder_type = data.holder_type.value
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="trade_licence.updated",
            entity_type="trade_licence",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=_snapshot(row),
        )
        self._session.commit()
        return row

    def delete_licence(
        self, licence_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Withdraw a licence recorded by mistake.

        An expired licence is not deleted -- it stays as the record of what
        was valid when a past sale was made; this is for a wrong entry.
        """
        row = self.get_licence(licence_id, firm_id=firm_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="trade_licence.deleted",
            entity_type="trade_licence",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=_snapshot(row),
        )
        self._session.commit()

    def list_licences(
        self,
        *,
        firm_id: UUID,
        holder_type: LicenceHolderType | None = None,
        branch_id: UUID | None = None,
        customer_id: UUID | None = None,
        vendor_id: UUID | None = None,
        licence_type_id: UUID | None = None,
        expiring_within_days: int | None = None,
        on: date | None = None,
    ) -> list[TradeLicenceResponse]:
        """Return the register, filtered, the firm's own first, then by expiry.

        ``expiring_within_days`` keeps what runs out within that many days of
        ``on`` -- already expired included, since an expired licence is the
        more urgent case.
        """
        today = on or utc_now().date()
        query = select(TradeLicence).where(
            TradeLicence.firm_id == firm_id,
            TradeLicence.is_deleted.is_(False),
        )
        if holder_type is not None:
            query = query.where(TradeLicence.holder_type == holder_type.value)
        if branch_id is not None:
            query = query.where(TradeLicence.branch_id == branch_id)
        if customer_id is not None:
            query = query.where(TradeLicence.customer_id == customer_id)
        if vendor_id is not None:
            query = query.where(TradeLicence.vendor_id == vendor_id)
        if licence_type_id is not None:
            query = query.where(TradeLicence.licence_type_id == licence_type_id)
        rows = list(self._session.scalars(query).all())
        types = {
            row.id: row
            for row in self._session.scalars(
                select(TradeLicenceType).where(TradeLicenceType.firm_id == firm_id)
            ).all()
        }
        responses = self.responses(rows, types=types, on=today)
        if expiring_within_days is not None:
            responses = [
                item
                for item in responses
                if item.days_to_expiry is not None
                and item.days_to_expiry <= expiring_within_days
            ]
        order = {"FIRM": 0, "CUSTOMER": 1, "VENDOR": 2}
        # Never NULL ordering in the database: sorted here, no-expiry last.
        responses.sort(
            key=lambda item: (
                order[item.holder_type.value],
                item.valid_to is None,
                item.valid_to or date.max,
                item.licence_number,
            )
        )
        return responses

    def responses(
        self,
        rows: list[TradeLicence],
        *,
        types: dict[UUID, TradeLicenceType] | None = None,
        on: date | None = None,
    ) -> list[TradeLicenceResponse]:
        """Describe licences with their type, holder and standing."""
        today = on or utc_now().date()
        if types is None:
            ids = {row.licence_type_id for row in rows}
            types = {
                row.id: row
                for row in self._session.scalars(
                    select(TradeLicenceType).where(TradeLicenceType.id.in_(ids))
                ).all()
            }
        names = self._holder_names(rows)
        result: list[TradeLicenceResponse] = []
        for row in rows:
            licence_type = types[row.licence_type_id]
            standing, days = standing_of(row, licence_type, on=today)
            holder_id = row.customer_id or row.vendor_id or row.branch_id
            result.append(
                TradeLicenceResponse(
                    id=row.id,
                    version=row.version,
                    licence_type_id=row.licence_type_id,
                    licence_type_code=licence_type.code,
                    licence_type_name=licence_type.name,
                    holder_type=LicenceHolderType(row.holder_type),
                    branch_id=row.branch_id,
                    customer_id=row.customer_id,
                    vendor_id=row.vendor_id,
                    holder_name=(
                        names.get(holder_id, "") if holder_id is not None else "Firm"
                    ),
                    licence_number=row.licence_number,
                    issued_by=row.issued_by,
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                    premises=row.premises,
                    remarks=row.remarks,
                    standing=standing,
                    days_to_expiry=days,
                )
            )
        return result

    def _holder_names(self, rows: list[TradeLicence]) -> dict[UUID, str]:
        """Read every holder's name in one query per kind, never per row."""
        names: dict[UUID, str] = {}
        customers = {row.customer_id for row in rows if row.customer_id}
        vendors = {row.vendor_id for row in rows if row.vendor_id}
        branches = {row.branch_id for row in rows if row.branch_id}
        if customers:
            names.update(
                self._session.execute(
                    select(Customer.id, Customer.display_name).where(
                        Customer.id.in_(customers)
                    )
                )
                .tuples()
                .all()
            )
        if vendors:
            names.update(
                self._session.execute(
                    select(Vendor.id, Vendor.display_name).where(Vendor.id.in_(vendors))
                )
                .tuples()
                .all()
            )
        if branches:
            names.update(
                self._session.execute(
                    select(Branch.id, Branch.display_name).where(
                        Branch.id.in_(branches)
                    )
                )
                .tuples()
                .all()
            )
        return names

    def valid_numbers(
        self,
        *,
        firm_id: UUID,
        on: date,
        branch_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> list[tuple[str, str]]:
        """Return ``(type name, number)`` of licences valid on a day.

        For printing: the firm's own (the whole firm's and, given a branch,
        that branch's) or a customer's. A licence that has run out, or has
        not started, is not printed -- a document states what was valid when
        it was made.
        """
        query = (
            select(TradeLicence, TradeLicenceType)
            .join(
                TradeLicenceType,
                TradeLicenceType.id == TradeLicence.licence_type_id,
            )
            .where(
                TradeLicence.firm_id == firm_id,
                TradeLicence.is_deleted.is_(False),
            )
        )
        if customer_id is not None:
            query = query.where(TradeLicence.customer_id == customer_id)
        else:
            query = query.where(TradeLicence.holder_type == "FIRM")
            query = query.where(
                (TradeLicence.branch_id.is_(None))
                | (TradeLicence.branch_id == branch_id)
            )
        printed: list[tuple[str, str]] = []
        for licence, licence_type in self._session.execute(query).tuples():
            standing, _ = standing_of(licence, licence_type, on=on)
            if standing in (LicenceStanding.EXPIRED, LicenceStanding.NOT_YET_VALID):
                continue
            printed.append((licence_type.name, licence.licence_number))
        return sorted(printed)
