"""The brands a supplier may sell (backlog 129, row M11).

A supplier names brands, and the product list of a purchase order placed on
it is narrowed to them. The list narrows what is offered; it never refuses
a line, because a firm's first order for a new brand is raised before
anybody has tidied the master.

Which brands count for a supplier is answered in this order, and the first
that has any brand wins:

1. the brands named on the supplier itself (``OWN``);
2. the brands of every company (principal) that names this supplier as the
   one it is bought from (``COMPANY``);
3. for a branch, whatever its main office answers (``MAIN_OFFICE``).

A stockist who sells other companies' brands is a supplier with the brands
he is allowed named on him: rule 1, and whose brands they are does not
matter. A supplier nothing answers for is not limited at all (``NONE``).
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.products.models.brand import Brand, Principal
from app.vendors.models import Vendor
from app.vendors.models.vendor_brand import VendorBrand

BrandSource = Literal["OWN", "COMPANY", "MAIN_OFFICE", "NONE"]


class VendorBrandsWrite(BaseModel):
    """The whole list of brands named on one supplier; empty clears it."""

    model_config = ConfigDict(extra="forbid")

    brand_ids: list[UUID] = Field(max_length=2000)


class VendorBrandRow(BaseModel):
    """One brand a supplier may sell, with the company that owns it."""

    model_config = ConfigDict(extra="forbid")

    brand_id: UUID
    name: str
    principal_id: UUID | None
    principal_name: str | None
    is_active: bool


class VendorBrandList(BaseModel):
    """What a supplier may sell, and where that answer came from."""

    model_config = ConfigDict(extra="forbid")

    vendor_id: UUID
    #: Where ``brands`` came from; ``NONE`` means the supplier is not limited.
    source: BrandSource
    #: The supplier whose list was read when ``source`` is ``MAIN_OFFICE``.
    source_vendor_name: str | None = None
    #: The brands named on this supplier itself, as its form shows them.
    named_brand_ids: list[UUID]
    #: The brands that count for this supplier, by name.
    brands: list[VendorBrandRow]


class VendorBrandService:
    """Read and replace the brands a supplier may sell."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's session."""
        self._session = session

    def brands_of(self, vendor_id: UUID, *, firm_id: UUID) -> VendorBrandList:
        """Return the brands that count for a supplier, and their source."""
        vendor = self._vendor(vendor_id, firm_id=firm_id)
        named = self._named(vendor.id)
        source, ids = self._own_or_company(vendor.id, named)
        source_name: str | None = None
        if source == "NONE" and vendor.parent_vendor_id is not None:
            parent = self._session.get(Vendor, vendor.parent_vendor_id)
            if parent is not None and not parent.is_deleted:
                above, ids = self._own_or_company(parent.id, self._named(parent.id))
                if above != "NONE":
                    source, source_name = "MAIN_OFFICE", parent.name
        return VendorBrandList(
            vendor_id=vendor.id,
            source=source,
            source_vendor_name=source_name,
            named_brand_ids=named,
            brands=self._rows(ids, firm_id=firm_id),
        )

    def stage_set(
        self,
        vendor_id: UUID,
        data: VendorBrandsWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Replace the brands named on a supplier; flush, do not commit.

        Raises:
            ValidationError: If a brand named is not one of the firm's.

        """
        vendor = self._vendor(vendor_id, firm_id=firm_id)
        wanted = list(dict.fromkeys(data.brand_ids))
        known = set(self._live_brand_ids(wanted, firm_id=firm_id))
        if len(known) != len(wanted):
            raise ValidationError(
                "A brand named for this supplier is not one of the firm's brands."
            )
        rows = list(
            self._session.scalars(
                select(VendorBrand).where(VendorBrand.vendor_id == vendor.id)
            ).all()
        )
        before = sorted(str(row.brand_id) for row in rows)
        after = sorted(str(brand_id) for brand_id in wanted)
        if before == after:
            return
        for row in rows:
            if row.brand_id not in known:
                self._session.delete(row)
        held = {row.brand_id for row in rows}
        for brand_id in wanted:
            if brand_id not in held:
                self._session.add(
                    VendorBrand(
                        firm_id=firm_id,
                        vendor_id=vendor.id,
                        brand_id=brand_id,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
        self._session.flush()
        record_audit(
            self._session,
            action="vendor.brands_set",
            entity_type="vendor",
            entity_id=vendor.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"brand_ids": before},
            after_data={"brand_ids": after},
        )

    def set(
        self,
        vendor_id: UUID,
        data: VendorBrandsWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> VendorBrandList:
        """Replace the brands named on a supplier; commit."""
        self.stage_set(vendor_id, data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return self.brands_of(vendor_id, firm_id=firm_id)

    def supplier_naming(self, brand_id: UUID) -> str | None:
        """Return one live supplier that names a brand, for a refusal."""
        return self._session.scalar(
            select(Vendor.name)
            .join(VendorBrand, VendorBrand.vendor_id == Vendor.id)
            .where(VendorBrand.brand_id == brand_id, Vendor.is_deleted.is_(False))
            .order_by(Vendor.name.asc())
            .limit(1)
        )

    # ---- helpers -------------------------------------------------------

    def _own_or_company(
        self, vendor_id: UUID, named: list[UUID]
    ) -> tuple[BrandSource, list[UUID]]:
        """Answer rules 1 and 2 for one supplier."""
        if named:
            return "OWN", named
        company = list(
            self._session.scalars(
                select(Brand.id)
                .join(Principal, Principal.id == Brand.principal_id)
                .where(
                    Principal.vendor_id == vendor_id,
                    Principal.is_deleted.is_(False),
                    Brand.is_deleted.is_(False),
                )
            ).all()
        )
        if company:
            return "COMPANY", company
        return "NONE", []

    def _named(self, vendor_id: UUID) -> list[UUID]:
        """Return the live brands named on a supplier itself."""
        return list(
            self._session.scalars(
                select(VendorBrand.brand_id)
                .join(Brand, Brand.id == VendorBrand.brand_id)
                .where(
                    VendorBrand.vendor_id == vendor_id,
                    Brand.is_deleted.is_(False),
                )
                .order_by(Brand.name.asc())
            ).all()
        )

    def _live_brand_ids(self, ids: list[UUID], *, firm_id: UUID) -> list[UUID]:
        """Return which of these are the firm's live brands."""
        if not ids:
            return []
        return list(
            self._session.scalars(
                select(Brand.id).where(
                    Brand.id.in_(ids),
                    Brand.firm_id == firm_id,
                    Brand.is_deleted.is_(False),
                )
            ).all()
        )

    def _rows(self, ids: list[UUID], *, firm_id: UUID) -> list[VendorBrandRow]:
        """Shape brands by name, naming their companies in one read."""
        if not ids:
            return []
        found = self._session.execute(
            select(Brand, Principal.name)
            .outerjoin(Principal, Principal.id == Brand.principal_id)
            .where(
                Brand.id.in_(ids),
                Brand.firm_id == firm_id,
                Brand.is_deleted.is_(False),
            )
            .order_by(Brand.name.asc())
        ).all()
        return [
            VendorBrandRow(
                brand_id=brand.id,
                name=brand.name,
                principal_id=brand.principal_id,
                principal_name=principal_name,
                is_active=brand.is_active,
            )
            for brand, principal_name in found
        ]

    def _vendor(self, vendor_id: UUID, *, firm_id: UUID) -> Vendor:
        """Return the supplier, refusing one of another firm."""
        vendor = self._session.get(Vendor, vendor_id)
        if vendor is None or vendor.is_deleted or vendor.firm_id != firm_id:
            raise ResourceNotFoundError("Supplier not found.")
        return vendor
