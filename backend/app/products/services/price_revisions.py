"""Price revisions with an effective date (MST-2, decision A119).

"New rates from the 1st": a revision names a product, a date and any of its
selling price, purchase price and MRP. Every document asks for the rate in
force on its own date -- the latest revision dated on or before it that
names that price -- and falls back to the product's own price before the
first. Revisions are never edited; one typed in error is deleted. A file of
revisions comes in through ``app.common.file_import``.

Three rules a revision keeps (D-PRC-15), typed or from a file:

* **It starts today or later**, on the firm's own day. One dated back was
  taken in silence and became today's price -- a product reading 84.00 was
  quoted at 70.00 -- and nothing on screen said a price had changed.
* **The MRP stays at or above the selling price**, as the product's own
  record insists, judged against whichever of the two the revision leaves
  alone: the one in force on the revision's date.
* **The product says what it sells at today.** `prices_in_force_today` gives
  a page of products their prices as the revisions leave them, so the card
  price and the price a document takes are both on the record.
"""

# ruff: noqa: D102, D107

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.file_import import (
    Column,
    FileImporter,
    ImportIssue,
    ImportReport,
    ImportRow,
    RowReader,
    parse_date,
    schema_issues,
    service_issue,
)
from app.common.firm_metadata import firm_today
from app.core.exceptions import (
    ApplicationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import utc_now
from app.products.models import Product
from app.products.models.price_revision import ProductPriceRevision

_FIELDS = ("selling_price", "purchase_price", "mrp")


def price_in_force(
    session: Session, product_id: UUID, field: str, *, on: date
) -> Decimal | None:
    """Return the revised ``field`` in force on ``on``, or None before any."""
    column = getattr(ProductPriceRevision, field)
    value = session.scalar(
        select(column)
        .where(
            ProductPriceRevision.product_id == product_id,
            ProductPriceRevision.effective_from <= on,
            ProductPriceRevision.is_deleted.is_(False),
            column.is_not(None),
        )
        .order_by(ProductPriceRevision.effective_from.desc())
        .limit(1)
    )
    return None if value is None else Decimal(str(value))


def prices_in_force_today(
    session: Session, firm_id: UUID, product_ids: Iterable[UUID]
) -> dict[UUID, dict[str, Decimal]]:
    """Return what the revisions make each product's prices today.

    One read for a page of products. A product no revision has reached is
    absent, and so is a price no revision names: its own price stands.

    Args:
        session: The firm's session.
        firm_id: The firm, whose own calendar says what today is.
        product_ids: The products on the page.

    Returns:
        ``{product id: {field: price}}`` for the fields in ``_FIELDS`` that a
        revision dated today or earlier names.

    """
    wanted = set(product_ids)
    if not wanted:
        return {}
    today = firm_today(session, firm_id)
    found: dict[UUID, dict[str, Decimal]] = {}
    for row in session.execute(
        select(
            ProductPriceRevision.product_id,
            ProductPriceRevision.selling_price,
            ProductPriceRevision.purchase_price,
            ProductPriceRevision.mrp,
        )
        .where(
            ProductPriceRevision.product_id.in_(wanted),
            ProductPriceRevision.firm_id == firm_id,
            ProductPriceRevision.effective_from <= today,
            ProductPriceRevision.is_deleted.is_(False),
        )
        .order_by(ProductPriceRevision.effective_from.asc())
    ):
        # Oldest first, so the latest revision naming a price is what is left.
        held = found.setdefault(row.product_id, {})
        for field in _FIELDS:
            value = getattr(row, field)
            if value is not None:
                held[field] = Decimal(str(value))
    return found


_MRP_RULE = "MRP must be greater than or equal to selling price."


class PriceRevisionWrite(BaseModel):
    """New rates from a date; at least one price."""

    model_config = ConfigDict(extra="forbid")

    effective_from: date
    selling_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    purchase_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    mrp: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    remarks: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _some_price(self) -> "PriceRevisionWrite":
        """Refuse a revision that revises nothing."""
        if all(getattr(self, field) is None for field in _FIELDS):
            raise ValueError("A revision names at least one new price.")
        return self

    @model_validator(mode="after")
    def _mrp_covers_the_price(self) -> "PriceRevisionWrite":
        """Refuse an MRP below the selling price, as the product does."""
        if (
            self.mrp is not None
            and self.selling_price is not None
            and self.mrp < self.selling_price
        ):
            raise ValueError(_MRP_RULE)
        return self


class PriceRevisionResponse(BaseModel):
    """One revision, and whether it is the one in force today."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    product_id: UUID
    effective_from: date
    selling_price: Decimal | None
    purchase_price: Decimal | None
    mrp: Decimal | None
    remarks: str | None
    is_current: bool
    version: int


class PriceRevisionService:
    """Keep one firm's price revisions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for(
        self, product_id: UUID, *, firm_id: UUID
    ) -> list[PriceRevisionResponse]:
        """Return a product's revisions, newest first."""
        self._product(product_id, firm_id)
        rows = list(
            self._session.scalars(
                select(ProductPriceRevision)
                .where(
                    ProductPriceRevision.product_id == product_id,
                    ProductPriceRevision.is_deleted.is_(False),
                )
                .order_by(ProductPriceRevision.effective_from.desc())
            ).all()
        )
        today = firm_today(self._session, firm_id)
        current = next((row.id for row in rows if row.effective_from <= today), None)
        return [
            PriceRevisionResponse(
                id=row.id,
                product_id=row.product_id,
                effective_from=row.effective_from,
                selling_price=row.selling_price,
                purchase_price=row.purchase_price,
                mrp=row.mrp,
                remarks=row.remarks,
                is_current=row.id == current,
                version=row.version,
            )
            for row in rows
        ]

    def add(
        self,
        product_id: UUID,
        data: PriceRevisionWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PriceRevisionResponse:
        """Add one revision and commit."""
        self.stage_add(product_id, data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return next(
            row
            for row in self.list_for(product_id, firm_id=firm_id)
            if row.effective_from == data.effective_from
        )

    def stage_add(
        self,
        product_id: UUID,
        data: PriceRevisionWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> ProductPriceRevision:
        """Add one revision without committing.

        Raises:
            ConflictError: If the product already has a revision that day.
            ValidationError: If it is dated before today, or would leave the
                MRP below the selling price.

        """
        product = self._product(product_id, firm_id)
        today = firm_today(self._session, firm_id)
        if data.effective_from < today:
            raise ValidationError(
                f"New rates start today ({today:%d-%m-%Y}) or later, not from "
                f"{data.effective_from:%d-%m-%Y}. A price dated back would "
                "change today's price without saying so; date it today instead."
            )
        self._assert_mrp_covers_the_price(product, data)
        clash = self._session.scalar(
            select(ProductPriceRevision.id).where(
                ProductPriceRevision.product_id == product_id,
                ProductPriceRevision.effective_from == data.effective_from,
                ProductPriceRevision.is_deleted.is_(False),
            )
        )
        if clash is not None:
            raise ConflictError(
                f"{product.code} already has new rates from "
                f"{data.effective_from:%d-%m-%Y}; delete that revision to correct it."
            )
        row = ProductPriceRevision(
            firm_id=firm_id,
            product_id=product_id,
            created_by=actor_id,
            updated_by=actor_id,
            **data.model_dump(),
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="product_price_revision.created",
            entity_type="product_price_revision",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "product": product.code,
                "effective_from": data.effective_from.isoformat(),
                **{
                    field: str(getattr(data, field))
                    for field in _FIELDS
                    if getattr(data, field) is not None
                },
            },
        )
        return row

    def _assert_mrp_covers_the_price(
        self, product: Product, data: PriceRevisionWrite
    ) -> None:
        """Hold the MRP rule against the price the revision leaves alone.

        The schema compares the two when one revision names both. Naming one
        of them must not cross the other as it stands on the revision's date:
        an earlier revision's, or the product's own.
        """
        if data.mrp is None and data.selling_price is None:
            return
        if data.mrp is not None and data.selling_price is not None:
            return

        def standing(field: str) -> Decimal | None:
            """Return ``field`` as it will stand from the revision's date."""
            sent: Decimal | None = getattr(data, field)
            if sent is not None:
                return sent
            revised = price_in_force(
                self._session, product.id, field, on=data.effective_from
            )
            if revised is not None:
                return revised
            stored = getattr(product, field)
            return None if stored is None else Decimal(str(stored))

        mrp, selling = standing("mrp"), standing("selling_price")
        if mrp is not None and selling is not None and mrp < selling:
            raise ValidationError(
                f"{_MRP_RULE} From {data.effective_from:%d-%m-%Y} {product.code} "
                f"would sell at {selling.normalize():f} against an MRP of "
                f"{mrp.normalize():f}."
            )

    def delete(
        self, product_id: UUID, revision_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Remove one revision typed in error."""
        row = self._session.get(ProductPriceRevision, revision_id)
        if (
            row is None
            or row.is_deleted
            or row.product_id != product_id
            or row.firm_id != firm_id
        ):
            raise ResourceNotFoundError("Price revision not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="product_price_revision.deleted",
            entity_type="product_price_revision",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._session.commit()

    def _product(self, product_id: UUID, firm_id: UUID) -> Product:
        """Return one of the firm's products."""
        row = self._session.get(Product, product_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Product not found.")
        return row


#: The revision file. ``Code`` is the product code the importer keys on.
COLUMNS: tuple[Column, ...] = (
    Column(
        "Code", ("productcode", "itemcode", "sku"), True, "Product code.", "RICE-25"
    ),
    Column(
        "EffectiveFrom",
        ("fromdate", "validfrom", "wef", "date"),
        True,
        "The date the new rates start.",
        "01-11-2026",
    ),
    Column(
        "SellingPrice",
        ("rate", "saleprice", "salesrate"),
        False,
        "New selling price.",
        "1500",
    ),
    Column(
        "PurchasePrice",
        ("costprice", "purchaserate"),
        False,
        "New purchase price.",
        "1350",
    ),
    Column("MRP", ("maximumretailprice",), False, "New MRP.", "1650"),
)

_HEADINGS = {
    "effective_from": "EffectiveFrom",
    "selling_price": "SellingPrice",
    "purchase_price": "PurchasePrice",
    "mrp": "MRP",
}


class PriceRevisionFileImporter(FileImporter[ProductPriceRevision]):
    """Bring a file of new rates in, all or nothing.

    One row per product per file; a product with a revision already that day
    is refused by name.
    """

    COLUMNS = COLUMNS
    NOUN = "price revision"

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._service = PriceRevisionService(session)
        self._products: dict[str, Product] = {}

    def _prepare(self, firm_id: UUID) -> None:
        self._products = {
            product.code.upper(): product
            for product in self._session.scalars(
                select(Product).where(
                    Product.firm_id == firm_id, Product.is_deleted.is_(False)
                )
            ).all()
        }

    def _stored(self, firm_id: UUID) -> dict[str, ProductPriceRevision]:
        # Every row is a new revision; there is nothing to "update" by code.
        return {}

    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: ProductPriceRevision | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[ProductPriceRevision],
    ) -> None:
        product = self._products.get(code)
        if product is None:
            report.issues.append(
                ImportIssue(row.number, code, "Code", "is not a product of this firm.")
            )
            return
        before = len(report.issues)
        reader = RowReader(row, code, report.issues)
        raw = reader.text("EffectiveFrom")
        effective = parse_date(raw) if raw else None
        if effective is None:
            reader.fail("EffectiveFrom", f"'{raw}' is not a date.")
        values = {
            "effective_from": effective,
            "selling_price": reader.number("SellingPrice"),
            "purchase_price": reader.number("PurchasePrice"),
            "mrp": reader.number("MRP"),
        }
        if len(report.issues) > before:
            return
        try:
            write = PriceRevisionWrite.model_validate(values)
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _HEADINGS))
            return
        try:
            staged = self._service.stage_add(
                product.id, write, firm_id=firm_id, actor_id=actor_id
            )
        except ApplicationError as error:
            report.issues.append(service_issue(error, row, code, _HEADINGS))
            return
        report.to_create += 1
        report.records.append(staged)

    def _commit(self) -> None:
        self._session.commit()
