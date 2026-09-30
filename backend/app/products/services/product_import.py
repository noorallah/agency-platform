"""Bring a firm's products in from a spreadsheet, with a template to fill in.

Backlog 46. The rules every master import keeps -- check every row, write all
or nothing, match headings loosely, update by code on request -- live in
``app.common.file_import``. What is particular to products:

* **References are matched, never guessed.** A category, unit or tax group is
  found by code or by name, ignoring case; one that is not there is reported.
* **Headings answer to the names other software exports** ("Item Code",
  "HSN/SAC", "Sale Price"), so an export needs little editing.
"""

# ruff: noqa: D102, D107

from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import file_import
from app.common.file_import import (
    Column,
    ExistingRows,
    FileImporter,
    ImportIssue,
    ImportReport,
    ImportRow,
    RowReader,
    schema_issues,
)
from app.core.exceptions import ApplicationError
from app.products.models import Product, ProductCategory
from app.products.schemas import ProductCreate, ProductUpdate
from app.products.schemas.product import ProductStatus, ProductType
from app.tax.models import TaxProfile
from app.uom.models import Uom

if TYPE_CHECKING:
    from app.products.services.product_service import ProductService

__all__ = [
    "COLUMNS",
    "ExistingRows",
    "ImportReport",
    "ProductFileImporter",
    "template_csv",
    "template_workbook",
]

#: The template, in the order it is laid out. The headings are what the notes
#: sheet explains and what every error names.
COLUMNS: tuple[Column, ...] = (
    Column(
        "Code",
        ("productcode", "itemcode", "sku", "partno", "partnumber"),
        True,
        "Unique product code: letters, digits, - and _ (made upper case).",
        "RICE-5KG",
    ),
    Column(
        "Name",
        ("productname", "itemname"),
        True,
        "Product name as it prints on documents.",
        "Basmati Rice 5 kg",
    ),
    Column(
        "Type",
        ("producttype", "itemtype"),
        False,
        "One of: "
        + ", ".join(item.value for item in ProductType)
        + ". Blank means STOCK_ITEM.",
        "STOCK_ITEM",
    ),
    Column(
        "Category",
        ("categorycode", "categoryname", "stockgroup", "group", "itemgroup"),
        False,
        "An existing category, by code or name (see the Lists sheet).",
        "GROCERY",
    ),
    Column(
        "SubCategory",
        ("subcategorycode", "subcategoryname", "subgroup"),
        False,
        "An existing sub category of that category, by code or name.",
        "",
    ),
    Column(
        "Unit",
        ("uom", "baseunit", "baseuom", "units", "unitofmeasure"),
        False,
        "An existing unit, by code, name or symbol (see the Lists sheet).",
        "PCS",
    ),
    Column(
        "HSN",
        ("hsnsac", "hsncode", "saccode", "sac"),
        False,
        "HSN or SAC code.",
        "10063020",
    ),
    Column(
        "TaxGroup",
        ("taxprofile", "taxprofilegroupcode", "gstgroup", "taxcategory"),
        False,
        "An active tax profile group code (see the Lists sheet).",
        "GST5",
    ),
    Column("Brand", ("make", "manufacturer"), False, "Brand name.", "Acme"),
    Column("Model", ("modelno", "modelnumber"), False, "Model.", ""),
    Column(
        "Barcode",
        ("ean", "upc", "gtin"),
        False,
        "Barcode; must be unique among the firm's products.",
        "",
    ),
    Column("ShortName", ("alias",), False, "Short name, 100 characters.", ""),
    Column("Description", ("details",), False, "Longer description.", ""),
    Column(
        "PurchasePrice",
        ("costprice", "cost", "purchaserate", "buyingprice"),
        False,
        "Number, no currency sign; commas are ignored.",
        "400",
    ),
    Column(
        "SellingPrice",
        ("saleprice", "salesprice", "salerate", "sellingrate", "rate", "price"),
        False,
        "Number; must not exceed MRP.",
        "450",
    ),
    Column("MRP", ("maximumretailprice",), False, "Number.", "499"),
    Column(
        "Status",
        (),
        False,
        "One of: "
        + ", ".join(item.value for item in ProductStatus)
        + ". Blank means ACTIVE.",
        "ACTIVE",
    ),
    Column(
        "TrackBatch",
        ("batchwise", "maintainbatches"),
        False,
        "Yes or No.",
        "No",
    ),
    Column("TrackExpiry", ("expirytracking",), False, "Yes or No.", "No"),
    Column(
        "TrackSerial",
        ("serialnumbers",),
        False,
        "Yes or No.",
        "No",
    ),
    Column(
        "AllowNegativeStock",
        ("negativestock",),
        False,
        "Yes or No.",
        "No",
    ),
    Column("Remarks", ("notes", "note"), False, "Free text.", ""),
)

#: The write-schema field each heading fills, for naming a schema refusal.
_FIELD_HEADINGS: dict[str, str] = {
    "code": "Code",
    "name": "Name",
    "product_type": "Type",
    "category_id": "Category",
    "sub_category_id": "SubCategory",
    "base_uom_id": "Unit",
    "unit": "Unit",
    "hsn_sac": "HSN",
    "tax_profile_group_code": "TaxGroup",
    "brand": "Brand",
    "model": "Model",
    "barcode": "Barcode",
    "short_name": "ShortName",
    "description": "Description",
    "purchase_price": "PurchasePrice",
    "selling_price": "SellingPrice",
    "mrp": "MRP",
    "status": "Status",
    "track_batch": "TrackBatch",
    "track_expiry": "TrackExpiry",
    "track_serial": "TrackSerial",
    "allow_negative_stock": "AllowNegativeStock",
    "remarks": "Remarks",
}

_TEXT_FIELDS: dict[str, str] = {
    "Brand": "brand",
    "Model": "model",
    "Barcode": "barcode",
    "ShortName": "short_name",
    "Description": "description",
    "Remarks": "remarks",
}
_MONEY_FIELDS: dict[str, str] = {
    "PurchasePrice": "purchase_price",
    "SellingPrice": "selling_price",
    "MRP": "mrp",
}
_FLAG_FIELDS: dict[str, str] = {
    "TrackBatch": "track_batch",
    "TrackExpiry": "track_expiry",
    "TrackSerial": "track_serial",
    "AllowNegativeStock": "allow_negative_stock",
}


class _References:
    """The firm's categories, units and tax groups, read once per file."""

    def __init__(self, session: Session, firm_id: UUID) -> None:
        categories = session.scalars(
            select(ProductCategory).where(
                ProductCategory.firm_id == firm_id,
                ProductCategory.is_deleted.is_(False),
            )
        ).all()
        self.categories = list(categories)
        units = session.scalars(
            select(Uom).where(Uom.is_deleted.is_(False), Uom.status == "ACTIVE")
        ).all()
        self.units: dict[str, Uom] = {}
        # Codes win over names and symbols: filled last so they overwrite.
        for unit in units:
            if unit.symbol:
                self.units.setdefault(unit.symbol.strip().lower(), unit)
        for unit in units:
            self.units[unit.name.strip().lower()] = unit
        for unit in units:
            self.units[unit.code.strip().lower()] = unit
        self.tax_groups = {
            code.upper(): code
            for code in session.scalars(
                select(TaxProfile.group_code).where(
                    TaxProfile.firm_id == firm_id,
                    TaxProfile.is_deleted.is_(False),
                    TaxProfile.status == "ACTIVE",
                )
            ).all()
            if code
        }

    def category(self, value: str, parent_id: UUID | None) -> ProductCategory | None:
        """Find a category by code, then by name, under ``parent_id``.

        A top-level lookup (``parent_id`` None) accepts any category, so a
        firm whose masters are one level deep is not refused.
        """
        wanted = value.strip().lower()
        pool = [
            item
            for item in self.categories
            if parent_id is None or item.parent_id == parent_id
        ]
        by_code = [item for item in pool if item.code.lower() == wanted]
        by_name = [item for item in pool if item.name.strip().lower() == wanted]
        for found in (by_code, by_name):
            if found:
                # Prefer the shallowest: a top-level category of that name
                # over a sub category somewhere else that shares it.
                return min(found, key=lambda item: item.level)
        return None


class ProductFileImporter(FileImporter[Product]):
    """Check a product file row by row, and import it whole or not at all."""

    COLUMNS = COLUMNS
    NOUN = "product"

    def __init__(self, session: Session, service: "ProductService") -> None:
        super().__init__(session)
        self._service = service
        self._references: _References | None = None

    def _prepare(self, firm_id: UUID) -> None:
        self._references = _References(self._session, firm_id)

    def _stored(self, firm_id: UUID) -> dict[str, Product]:
        return {
            product.code: product
            for product in self._session.scalars(
                select(Product).where(
                    Product.firm_id == firm_id, Product.is_deleted.is_(False)
                )
            ).all()
        }

    def _commit(self) -> None:
        self._service._commit()

    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: Product | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[Product],
    ) -> None:
        issues: list[ImportIssue] = []
        values = self._values(RowReader(row, code, issues), code, current)
        if issues:
            report.issues.extend(issues)
            return
        try:
            data = (
                ProductCreate.model_validate(values)
                if current is None
                else ProductUpdate.model_validate(values)
            )
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _FIELD_HEADINGS))
            return
        try:
            if isinstance(data, ProductCreate):
                product = self._service.stage_product(
                    data, firm_id=firm_id, actor_id=actor_id
                )
                report.to_create += 1
            elif current is not None:
                product = self._service.stage_update_product(
                    current, data, firm_scope=firm_id, actor_id=actor_id
                )
                report.to_update += 1
        except ApplicationError as error:
            # The guards all run before the row is added, so the session is
            # still sound and the rest of the file can be checked.
            report.issues.append(ImportIssue(row.number, code, None, error.message))
            return
        report.records.append(product)

    def _values(
        self, reader: RowReader, code: str, current: Product | None
    ) -> dict[str, object]:
        """Turn one row's cells into write-schema values.

        On a create a blank cell takes the schema default. On an update a blank
        cell -- or a column the file does not have -- is left out, so it leaves
        the stored value alone.
        """
        values: dict[str, object] = {"code": code}
        name = reader.text("Name")
        if name:
            values["name"] = name
        elif current is None:
            reader.fail("Name", "is required.")
        else:
            values["name"] = current.name
        kind = reader.text("Type").upper().replace(" ", "_")
        if kind:
            values["product_type"] = kind
        else:
            values["product_type"] = (
                current.product_type if current is not None else "STOCK_ITEM"
            )
        status = reader.text("Status").upper()
        if status:
            values["status"] = status
        for heading, target in _TEXT_FIELDS.items():
            if reader.text(heading):
                values[target] = reader.text(heading)
        hsn = reader.text("HSN")
        if hsn:
            values["hsn_sac"] = hsn.upper()
        for heading, target in _MONEY_FIELDS.items():
            amount = reader.number(heading)
            if amount is not None:
                values[target] = amount
        for heading, target in _FLAG_FIELDS.items():
            flag = reader.flag(heading)
            if flag is not None:
                values[target] = flag
        assert self._references is not None
        self._resolve(reader.cells, current, self._references, values, reader.fail)
        return values

    @staticmethod
    def _resolve(
        cells: dict[str, str],
        current: Product | None,
        references: _References,
        values: dict[str, object],
        fail: Callable[[str, str], None],
    ) -> None:
        """Turn category, unit and tax group names into what the schema takes."""
        category_id: UUID | None = current.category_id if current else None
        category_text = cells.get("Category", "")
        if category_text:
            category = references.category(category_text, None)
            if category is None:
                fail("Category", f"'{category_text}' is not one of the firm's.")
            else:
                category_id = category.id
                values["category_id"] = category.id
        sub_text = cells.get("SubCategory", "")
        if sub_text:
            if category_id is None:
                fail("SubCategory", "needs a Category.")
            else:
                sub = references.category(sub_text, category_id)
                if sub is None:
                    fail(
                        "SubCategory",
                        f"'{sub_text}' is not a sub category of that category.",
                    )
                else:
                    values["sub_category_id"] = sub.id
        elif (
            category_text
            and current is not None
            and category_id != (current.category_id)
        ):
            # A new category cannot keep the old one's sub category.
            values["sub_category_id"] = None
        unit_text = cells.get("Unit", "")
        if unit_text:
            unit = references.units.get(unit_text.strip().lower())
            if unit is None:
                fail("Unit", f"'{unit_text}' is not a unit on this system.")
            else:
                values["unit"] = unit.code
                values["base_uom_id"] = unit.id
                # A new product is one unit throughout until packaging is set
                # up; an existing one keeps any other units it already has.
                for target in ("inventory_uom_id", "purchase_uom_id", "sales_uom_id"):
                    if current is None or getattr(current, target) is None:
                        values[target] = unit.id
        tax_text = cells.get("TaxGroup", "")
        if tax_text:
            group = references.tax_groups.get(tax_text.strip().upper())
            if group is None:
                fail("TaxGroup", f"'{tax_text}' is not an active tax group.")
            else:
                values["tax_profile_group_code"] = group


def template_workbook(session: Session, firm_id: UUID) -> bytes:
    """Build the XLSX template: the sheet to fill, the notes, and the lists."""
    references = _References(session, firm_id)
    parents = {item.id: item.code for item in references.categories}
    categories = sorted(references.categories, key=lambda item: item.path)
    units = sorted(
        {unit.id: unit for unit in references.units.values()}.values(),
        key=lambda unit: unit.code,
    )
    return file_import.template_workbook(
        sheet_title="Products",
        columns=COLUMNS,
        notes=["Opening stock is imported separately, under Inventory."],
        lists_header=[
            "Category code",
            "Category name",
            "Parent",
            "",
            "Unit code",
            "Unit name",
            "",
            "Tax group",
        ],
        lists=[
            [item.code for item in categories],
            [item.name for item in categories],
            [
                parents.get(item.parent_id) if item.parent_id else None
                for item in categories
            ],
            [],
            [unit.code for unit in units],
            [unit.name for unit in units],
            [],
            sorted(references.tax_groups.values()),
        ],
    )


def template_csv() -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(COLUMNS)
