"""Principal and brand masters (MST-1, decision A118).

A product names its brand by row (``products.brand_id``); its free-text
``brand`` is kept in step with the row's name, so prints and search that read
the text still read the brand. A brand belongs to a principal -- the company
whose agency the firm holds -- and a principal may be a supplier.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.products.models import Product
from app.products.models.brand import Brand, Principal


class PrincipalWrite(BaseModel):
    """Create or change one principal."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    vendor_id: UUID | None = None
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def upper_code(cls, value: str) -> str:
        """Match codes regardless of case."""
        return value.strip().upper()


class PrincipalResponse(BaseModel):
    """One principal."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    code: str
    name: str
    vendor_id: UUID | None
    is_active: bool
    version: int


class BrandWrite(BaseModel):
    """Create or change one brand."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    principal_id: UUID | None = None
    is_active: bool = True


class BrandResponse(BaseModel):
    """One brand, with its principal named."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    principal_id: UUID | None
    principal_name: str | None
    is_active: bool
    version: int


class BrandService:
    """Keep principals and brands."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's session."""
        self._session = session

    # -- principals -----------------------------------------------------
    def principals(self, firm_id: UUID) -> list[PrincipalResponse]:
        """Return the firm's principals by name."""
        return [
            PrincipalResponse.model_validate(row)
            for row in self._session.scalars(
                select(Principal)
                .where(Principal.firm_id == firm_id, Principal.is_deleted.is_(False))
                .order_by(Principal.name.asc())
            ).all()
        ]

    def save_principal(
        self,
        data: PrincipalWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        principal_id: UUID | None = None,
    ) -> PrincipalResponse:
        """Create a principal, or change one; commit."""
        clash = self._session.scalar(
            select(Principal.id).where(
                Principal.firm_id == firm_id,
                Principal.code == data.code,
                Principal.is_deleted.is_(False),
            )
        )
        if clash is not None and clash != principal_id:
            raise ConflictError(f"There is already a principal {data.code}.")
        if principal_id is None:
            row = Principal(firm_id=firm_id, created_by=actor_id, **data.model_dump())
            self._session.add(row)
        else:
            row = self._principal(principal_id, firm_id)
            for field, value in data.model_dump().items():
                setattr(row, field, value)
        row.updated_by = actor_id
        self._session.flush()
        self._audit(
            "principal.saved", "principal", row.id, firm_id, actor_id, data.code
        )
        self._session.commit()
        return PrincipalResponse.model_validate(row)

    def delete_principal(
        self, principal_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Remove a principal no brand names.

        Raises:
            ValidationError: If a live brand belongs to it.

        """
        row = self._principal(principal_id, firm_id)
        held = self._session.scalar(
            select(Brand.name).where(
                Brand.principal_id == principal_id, Brand.is_deleted.is_(False)
            )
        )
        if held is not None:
            raise ValidationError(
                f"{row.name} still owns brand {held}; move or remove its brands first."
            )
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        self._audit(
            "principal.deleted", "principal", row.id, firm_id, actor_id, row.code
        )
        self._session.commit()

    # -- brands ---------------------------------------------------------
    def brands(self, firm_id: UUID) -> list[BrandResponse]:
        """Return the firm's brands by name."""
        rows = list(
            self._session.scalars(
                select(Brand)
                .where(Brand.firm_id == firm_id, Brand.is_deleted.is_(False))
                .order_by(Brand.name.asc())
            ).all()
        )
        return self._brand_responses(rows)

    def save_brand(
        self,
        data: BrandWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        brand_id: UUID | None = None,
    ) -> BrandResponse:
        """Create a brand, or rename one -- its products' text follows; commit."""
        name = data.name.strip()
        clash = self._session.scalar(
            select(Brand.id).where(
                Brand.firm_id == firm_id,
                Brand.name == name,
                Brand.is_deleted.is_(False),
            )
        )
        if clash is not None and clash != brand_id:
            raise ConflictError(f"There is already a brand {name}.")
        if data.principal_id is not None:
            self._principal(data.principal_id, firm_id)
        if brand_id is None:
            row = Brand(
                firm_id=firm_id,
                name=name,
                principal_id=data.principal_id,
                is_active=data.is_active,
                created_by=actor_id,
            )
            self._session.add(row)
        else:
            row = self._brand(brand_id, firm_id)
            row.name = name
            row.principal_id = data.principal_id
            row.is_active = data.is_active
            for product in self._session.scalars(
                select(Product).where(Product.brand_id == row.id)
            ).all():
                product.brand = name
        row.updated_by = actor_id
        self._session.flush()
        self._audit("brand.saved", "brand", row.id, firm_id, actor_id, name)
        self._session.commit()
        return self._brand_responses([row])[0]

    def delete_brand(self, brand_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove a brand no live product names.

        Raises:
            ValidationError: If a product still carries it.

        """
        row = self._brand(brand_id, firm_id)
        held = self._session.scalar(
            select(Product.code).where(
                Product.brand_id == brand_id, Product.is_deleted.is_(False)
            )
        )
        if held is not None:
            raise ValidationError(
                f"{row.name} is still the brand of {held}; change those products first."
            )
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        self._audit("brand.deleted", "brand", row.id, firm_id, actor_id, row.name)
        self._session.commit()

    def brand_name(self, brand_id: UUID | None, *, firm_id: UUID) -> str | None:
        """Return the name a product's text brand should carry, checking the id."""
        if brand_id is None:
            return None
        return self._brand(brand_id, firm_id).name

    def _brand_responses(self, rows: list[Brand]) -> list[BrandResponse]:
        """Shape brands, naming principals in one read."""
        ids = {row.principal_id for row in rows if row.principal_id}
        names: dict[UUID, str] = {}
        if ids:
            for row_id, name in self._session.execute(
                select(Principal.id, Principal.name).where(Principal.id.in_(ids))
            ).all():
                names[row_id] = name
        return [
            BrandResponse(
                id=row.id,
                name=row.name,
                principal_id=row.principal_id,
                principal_name=(
                    names.get(row.principal_id) if row.principal_id else None
                ),
                is_active=row.is_active,
                version=row.version,
            )
            for row in rows
        ]

    def _principal(self, principal_id: UUID, firm_id: UUID) -> Principal:
        """Return one of the firm's principals."""
        row = self._session.get(Principal, principal_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Principal not found.")
        return row

    def _brand(self, brand_id: UUID, firm_id: UUID) -> Brand:
        """Return one of the firm's brands."""
        row = self._session.get(Brand, brand_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Brand not found.")
        return row

    def _audit(
        self,
        action: str,
        entity: str,
        entity_id: UUID,
        firm_id: UUID,
        actor_id: UUID,
        label: str,
    ) -> None:
        """Write one audit row."""
        record_audit(
            self._session,
            action=action,
            entity_type=entity,
            entity_id=entity_id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"name": label},
        )
