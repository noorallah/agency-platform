"""A supplier's catalogue: their codes, prices and terms per product (BUY-4).

Decision A101. One dated row per supplier, product and ``effective_from``,
never overwritten: a new price is a new row, so the history stays readable,
and the row in force on a date is the latest one dated on or before it. A
purchase order line reads it for the supplier's code and, below a supplier
price list's fixed rate, for the price. A file of rows comes in through
``app.common.file_import`` like every other import.
"""

# ruff: noqa: D102, D107

from collections.abc import Iterable
from datetime import date
from uuid import UUID

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
)
from app.core.utils.dates import utc_now
from app.products.models import Product
from app.vendors.models import Vendor
from app.vendors.models.supplier_product import SupplierProduct
from app.vendors.schemas.supplier_product import (
    SupplierProductResponse,
    SupplierProductWrite,
)


def current_rows(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID,
    product_ids: Iterable[UUID] | None,
    on: date,
) -> dict[UUID, SupplierProduct]:
    """Return the row in force on ``on`` for each product, one query.

    ``product_ids`` None means every product the supplier lists.
    """
    query = (
        select(SupplierProduct)
        .where(
            SupplierProduct.firm_id == firm_id,
            SupplierProduct.vendor_id == vendor_id,
            SupplierProduct.effective_from <= on,
            SupplierProduct.is_deleted.is_(False),
        )
        .order_by(SupplierProduct.effective_from.asc())
    )
    if product_ids is not None:
        ids = list(set(product_ids))
        if not ids:
            return {}
        query = query.where(SupplierProduct.product_id.in_(ids))
    found: dict[UUID, SupplierProduct] = {}
    # Ascending, so the latest dated row for a product is the one kept.
    for row in session.scalars(query).all():
        found[row.product_id] = row
    return found


class SupplierCatalogueService:
    """List, add and remove one supplier's catalogue rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_rows(
        self, vendor_id: UUID, *, firm_id: UUID, history: bool = False
    ) -> list[SupplierProductResponse]:
        """Return the rows in force today, or with ``history`` every row."""
        self._vendor(vendor_id, firm_id=firm_id)
        today = utc_now().date()
        current = current_rows(
            self._session,
            firm_id=firm_id,
            vendor_id=vendor_id,
            product_ids=None,
            on=today,
        )
        current_ids = {row.id for row in current.values()}
        if history:
            rows = list(
                self._session.scalars(
                    select(SupplierProduct).where(
                        SupplierProduct.firm_id == firm_id,
                        SupplierProduct.vendor_id == vendor_id,
                        SupplierProduct.is_deleted.is_(False),
                    )
                ).all()
            )
        else:
            rows = list(current.values())
        return self.responses(rows, current_ids=current_ids)

    def add(
        self,
        vendor_id: UUID,
        data: SupplierProductWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> SupplierProductResponse:
        """Add one dated row and commit."""
        row = self.stage_add(vendor_id, data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return self.responses([row], current_ids=self._current_ids(row))[0]

    def stage_add(
        self,
        vendor_id: UUID,
        data: SupplierProductWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> SupplierProduct:
        """Add one dated row without committing.

        Raises:
            ResourceNotFoundError: If the supplier or product is not this firm's.
            ConflictError: If the supplier already has a row for the product
                from that date -- delete it first to correct it.

        """
        self._vendor(vendor_id, firm_id=firm_id)
        product = self._session.get(Product, data.product_id)
        if product is None or product.is_deleted or product.firm_id != firm_id:
            raise ResourceNotFoundError("Product not found.")
        clash = self._session.scalar(
            select(SupplierProduct.id).where(
                SupplierProduct.vendor_id == vendor_id,
                SupplierProduct.product_id == data.product_id,
                SupplierProduct.effective_from == data.effective_from,
                SupplierProduct.is_deleted.is_(False),
            )
        )
        if clash is not None:
            raise ConflictError(
                f"The supplier already has a row for {product.code} from "
                f"{data.effective_from:%d-%m-%Y}. A change is a new row from a "
                "later date; delete that one to correct it."
            )
        row = SupplierProduct(
            firm_id=firm_id,
            vendor_id=vendor_id,
            created_by=actor_id,
            updated_by=actor_id,
            **data.model_dump(),
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="supplier_product.created",
            entity_type="supplier_product",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "vendor_id": str(vendor_id),
                "product_id": str(data.product_id),
                "unit_price": None if data.unit_price is None else str(data.unit_price),
                "effective_from": data.effective_from.isoformat(),
            },
        )
        return row

    def delete(
        self, vendor_id: UUID, row_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Remove one row typed in error.

        Raises:
            ResourceNotFoundError: If it is not this supplier's.

        """
        row = self._session.get(SupplierProduct, row_id)
        if (
            row is None
            or row.is_deleted
            or row.vendor_id != vendor_id
            or row.firm_id != firm_id
        ):
            raise ResourceNotFoundError("Catalogue row not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="supplier_product.deleted",
            entity_type="supplier_product",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._session.commit()

    def responses(
        self, rows: list[SupplierProduct], *, current_ids: set[UUID]
    ) -> list[SupplierProductResponse]:
        """Shape rows for the wire, naming every product in one read."""
        ids = {row.product_id for row in rows}
        products = (
            {
                p.id: p
                for p in self._session.scalars(
                    select(Product).where(Product.id.in_(ids))
                ).all()
            }
            if ids
            else {}
        )
        ordered = sorted(
            rows,
            key=lambda r: (
                products[r.product_id].code if r.product_id in products else "",
                r.effective_from,
            ),
        )
        return [
            SupplierProductResponse(
                id=row.id,
                vendor_id=row.vendor_id,
                product_id=row.product_id,
                product_code=(
                    products[row.product_id].code if row.product_id in products else ""
                ),
                product_name=(
                    products[row.product_id].name if row.product_id in products else ""
                ),
                supplier_product_code=row.supplier_product_code,
                supplier_product_name=row.supplier_product_name,
                unit_price=row.unit_price,
                pack_size=row.pack_size,
                minimum_order_quantity=row.minimum_order_quantity,
                order_multiple=row.order_multiple,
                lead_time_days=row.lead_time_days,
                effective_from=row.effective_from,
                remarks=row.remarks,
                is_current=row.id in current_ids,
                created_at=row.created_at,
            )
            for row in ordered
        ]

    def _current_ids(self, row: SupplierProduct) -> set[UUID]:
        """Return the id of the row in force today for this row's product."""
        current = current_rows(
            self._session,
            firm_id=row.firm_id,
            vendor_id=row.vendor_id,
            product_ids=[row.product_id],
            on=utc_now().date(),
        )
        return {r.id for r in current.values()}

    def _vendor(self, vendor_id: UUID, *, firm_id: UUID) -> Vendor:
        """Return the supplier, refusing one of another firm."""
        vendor = self._session.get(Vendor, vendor_id)
        if vendor is None or vendor.is_deleted or vendor.firm_id != firm_id:
            raise ResourceNotFoundError("Supplier not found.")
        return vendor


#: The template. ``Code`` is the firm's own product code, which is what the
#: file importer keys every row on.
COLUMNS: tuple[Column, ...] = (
    Column(
        "Code",
        ("productcode", "itemcode", "sku", "ourcode"),
        True,
        "Your own product code, as the product master has it.",
        "RICE-25",
    ),
    Column(
        "SupplierCode",
        ("suppliercode", "vendoritemcode", "theircode", "partno", "partnumber"),
        False,
        "What the supplier calls it on their invoice.",
        "BR-25KG",
    ),
    Column(
        "SupplierName",
        ("supplieritemname", "vendoritemname", "description"),
        False,
        "The supplier's name for it.",
        "Basmati Rice 25 kg",
    ),
    Column(
        "Price",
        ("rate", "unitprice", "purchaseprice", "cost"),
        False,
        "Their price per purchase unit.",
        "1450",
    ),
    Column(
        "PackSize",
        ("pack", "casesize", "unitspercase"),
        False,
        "Units per pack or case as they ship it.",
        "10",
    ),
    Column(
        "MinimumOrder",
        ("moq", "minimumorderquantity", "minorder"),
        False,
        "The least they take an order for.",
        "20",
    ),
    Column(
        "OrderMultiple",
        ("multiple", "ordermultiple", "packmultiple"),
        False,
        "They ship only in multiples of this.",
        "10",
    ),
    Column(
        "LeadTimeDays",
        ("leadtime", "deliverydays"),
        False,
        "Days from order to delivery.",
        "5",
    ),
    Column(
        "EffectiveFrom",
        ("fromdate", "validfrom", "wef"),
        False,
        "The date these terms start; blank is today.",
        "01-04-2026",
    ),
)

_HEADINGS = {
    "product_id": "Code",
    "supplier_product_code": "SupplierCode",
    "supplier_product_name": "SupplierName",
    "unit_price": "Price",
    "pack_size": "PackSize",
    "minimum_order_quantity": "MinimumOrder",
    "order_multiple": "OrderMultiple",
    "lead_time_days": "LeadTimeDays",
    "effective_from": "EffectiveFrom",
}


class SupplierCatalogueFileImporter(FileImporter[SupplierProduct]):
    """Bring one supplier's catalogue rows in from a file, all or nothing.

    A product already listed is refused unless the file is to update; then
    its row is a new dated row, as a change by hand is.
    """

    COLUMNS = COLUMNS
    NOUN = "catalogue product"

    def __init__(self, session: Session, vendor_id: UUID) -> None:
        super().__init__(session)
        self._vendor_id = vendor_id
        self._service = SupplierCatalogueService(session)
        self._products: dict[str, Product] = {}

    def _prepare(self, firm_id: UUID) -> None:
        self._service._vendor(self._vendor_id, firm_id=firm_id)
        self._products = {
            product.code.upper(): product
            for product in self._session.scalars(
                select(Product).where(
                    Product.firm_id == firm_id, Product.is_deleted.is_(False)
                )
            ).all()
        }

    def _stored(self, firm_id: UUID) -> dict[str, SupplierProduct]:
        rows = current_rows(
            self._session,
            firm_id=firm_id,
            vendor_id=self._vendor_id,
            product_ids=None,
            on=date.max,
        )
        codes = {p.id: code for code, p in self._products.items()}
        return {codes[pid]: row for pid, row in rows.items() if pid in codes}

    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: SupplierProduct | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[SupplierProduct],
    ) -> None:
        product = self._products.get(code)
        if product is None:
            report.issues.append(
                ImportIssue(row.number, code, "Code", "is not a product of this firm.")
            )
            return
        before = len(report.issues)
        reader = RowReader(row, code, report.issues)
        raw_date = reader.text("EffectiveFrom")
        effective = (
            parse_date(raw_date) if raw_date else firm_today(self._session, firm_id)
        )
        if raw_date and effective is None:
            reader.fail("EffectiveFrom", f"'{raw_date}' is not a date.")
        values = {
            "product_id": product.id,
            "supplier_product_code": reader.text("SupplierCode") or None,
            "supplier_product_name": reader.text("SupplierName") or None,
            "unit_price": reader.number("Price"),
            "pack_size": reader.number("PackSize"),
            "minimum_order_quantity": reader.number("MinimumOrder"),
            "order_multiple": reader.number("OrderMultiple"),
            "lead_time_days": reader.whole("LeadTimeDays"),
            "effective_from": effective,
        }
        if len(report.issues) > before:
            return
        try:
            write = SupplierProductWrite.model_validate(values)
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _HEADINGS))
            return
        try:
            staged = self._service.stage_add(
                self._vendor_id, write, firm_id=firm_id, actor_id=actor_id
            )
        except ApplicationError as error:
            report.issues.append(service_issue(error, row, code, _HEADINGS))
            return
        if current is None:
            report.to_create += 1
        else:
            report.to_update += 1
        report.records.append(staged)

    def _commit(self) -> None:
        self._session.commit()
