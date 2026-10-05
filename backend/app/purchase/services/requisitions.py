"""Purchase requisitions and turning them into orders (BUY-7, decision A109).

A requisition is raised by whoever needs the goods -- a branch, a storeman,
the reorder screen -- submitted, and approved by somebody who may approve
purchases. Approving commits the firm to nothing: *Convert to orders* does,
raising one draft purchase order per supplier through the order's own save
path, every line priced from the supplier's terms. A line names its
supplier, or takes the product's preferred one; a line with neither is
refused by name. Once converted the requisition is ORDERED and is history.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.products.models import Product
from app.purchase.models import PurchaseOrder
from app.purchase.models.requisition import (
    PurchaseRequisition,
    PurchaseRequisitionLine,
)
from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.schemas.requisition import (
    PurchaseRequisitionLineResponse,
    PurchaseRequisitionResponse,
    PurchaseRequisitionWrite,
)

ZERO = Decimal("0")


class PurchaseRequisitionService(TransactionalDocumentService):
    """Raise, approve and convert purchase requisitions."""

    DOCUMENT = DocumentTypeSpec(
        code="PURCHASE_REQUISITION",
        name="Purchase Requisition",
        description="A request for goods, before any order.",
        category="PURCHASE",
        module="purchase",
        prefix="PR",
        rule_code="PURCHASE_REQUISITION_DEFAULT",
        rule_name="Purchase Requisition Default Numbering",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 10, allows_edit=True),
            DocumentStateSpec("SUBMITTED", "Submitted", 15, allows_edit=True),
            DocumentStateSpec("APPROVED", "Approved", 20),
            DocumentStateSpec("ORDERED", "Ordered", 80, is_terminal=True),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
        ),
    )

    # -- writing --------------------------------------------------------
    def create(
        self, data: PurchaseRequisitionWrite, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseRequisition:
        """Raise a draft requisition and commit."""
        row = self.stage_create(data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_create(
        self, data: PurchaseRequisitionWrite, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseRequisition:
        """Raise a draft requisition without committing."""
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        branch_code, company_code = self._scope_codes(
            firm_id=firm_id, branch_id=data.branch_id
        )
        number = self._issue_number(
            rule,
            typed=None,
            number_column=PurchaseRequisition.requisition_number,
            firm_id=firm_id,
            document_date=data.requisition_date,
            actor_id=actor_id,
            branch_code=branch_code,
            company_code=company_code,
        )
        row = PurchaseRequisition(
            firm_id=firm_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            requisition_number=number,
            requisition_date=data.requisition_date,
            needed_by=data.needed_by,
            status="DRAFT",
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Requisition number already exists in this firm.")
        self._write_lines(row, data, actor_id=actor_id)
        self._audit("purchase_requisition.created", row, actor_id)
        return row

    def update(
        self,
        requisition_id: UUID,
        data: PurchaseRequisitionWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PurchaseRequisition:
        """Change a draft or submitted requisition; a submitted one goes back."""
        row = self.get(requisition_id, firm_id=firm_id)
        if row.status not in ("DRAFT", "SUBMITTED"):
            raise ValidationError(
                f"A {row.status.lower()} requisition cannot be changed."
            )
        row.branch_id = data.branch_id
        row.warehouse_id = data.warehouse_id
        row.requisition_date = data.requisition_date
        row.needed_by = data.needed_by
        row.remarks = data.remarks
        row.status = "DRAFT"
        row.updated_by = actor_id
        self._write_lines(row, data, actor_id=actor_id)
        self._audit("purchase_requisition.updated", row, actor_id)
        self._session.commit()
        return row

    def submit(
        self, requisition_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseRequisition:
        """Send a draft for approval."""
        return self._move(requisition_id, "DRAFT", "SUBMITTED", firm_id, actor_id)

    def approve(
        self, requisition_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseRequisition:
        """Approve a submitted requisition."""
        row = self._move(
            requisition_id, "SUBMITTED", "APPROVED", firm_id, actor_id, commit=False
        )
        row.approved_by = actor_id
        row.approved_at = utc_now()
        self._session.commit()
        return row

    def cancel(
        self, requisition_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseRequisition:
        """Call off a requisition not yet ordered.

        Raises:
            ValidationError: If it was already ordered or cancelled, or no
                reason is given.

        """
        row = self.get(requisition_id, firm_id=firm_id)
        if row.status in ("ORDERED", "CANCELLED"):
            raise ValidationError(
                f"A {row.status.lower()} requisition cannot be cancelled."
            )
        if not reason.strip():
            raise ValidationError("Say why the requisition is cancelled.")
        row.status = "CANCELLED"
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._audit("purchase_requisition.cancelled", row, actor_id)
        self._session.commit()
        return row

    def convert_to_orders(
        self, requisition_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> list[PurchaseOrder]:
        """Raise one draft order per supplier for an approved requisition.

        Raises:
            ValidationError: If it is not approved, or a line has no supplier
                of its own and its product names no preferred one.

        """
        from app.purchase.services import PurchaseService

        row = self.get(requisition_id, firm_id=firm_id)
        if row.status != "APPROVED":
            raise ValidationError("Only an approved requisition is converted.")
        lines = self._lines(row.id)
        products = self._products({line.product_id for line in lines})
        grouped: dict[UUID, list[PurchaseRequisitionLine]] = defaultdict(list)
        orphans: list[str] = []
        for line in lines:
            product = products.get(line.product_id)
            supplier = line.vendor_id or (
                product.preferred_vendor_id if product else None
            )
            if supplier is None:
                orphans.append(product.code if product else str(line.product_id))
                continue
            grouped[supplier].append(line)
        if orphans:
            raise ValidationError(
                "Name a supplier for "
                + ", ".join(orphans)
                + " -- neither the line nor the product names one."
            )
        orders = PurchaseService(self._session)
        raised: list[PurchaseOrder] = []
        for supplier, supplier_lines in grouped.items():
            order = orders.stage_order(
                PurchaseOrderCreate.model_validate(
                    {
                        "branch_id": row.branch_id,
                        "warehouse_id": row.warehouse_id,
                        "vendor_id": supplier,
                        "purchase_date": utc_now().date(),
                        "expected_delivery_date": row.needed_by,
                        "reference_number": row.requisition_number,
                        "remarks": f"From requisition {row.requisition_number}",
                        "lines": [
                            {
                                "product_id": line.product_id,
                                "ordered_quantity": line.quantity,
                                "remarks": line.remarks,
                            }
                            for line in supplier_lines
                        ],
                    }
                ),
                firm_id=firm_id,
                actor_id=actor_id,
            )
            for line in supplier_lines:
                line.purchase_order_id = order.id
                line.updated_by = actor_id
            raised.append(order)
        row.status = "ORDERED"
        row.updated_by = actor_id
        self._audit("purchase_requisition.ordered", row, actor_id)
        self._session.commit()
        return raised

    # -- reading --------------------------------------------------------
    def get(self, requisition_id: UUID, *, firm_id: UUID) -> PurchaseRequisition:
        """Return one of the firm's requisitions."""
        row = self._session.get(PurchaseRequisition, requisition_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Purchase requisition not found.")
        return row

    def page(
        self,
        firm_id: UUID,
        *,
        status: str | None = None,
        page: int,
        page_size: int,
    ) -> tuple[list[PurchaseRequisition], int]:
        """Return one page of the firm's requisitions, newest first, and the count."""
        query = select(PurchaseRequisition).where(
            PurchaseRequisition.firm_id == firm_id,
            PurchaseRequisition.is_deleted.is_(False),
        )
        if status:
            query = query.where(PurchaseRequisition.status == status)
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._session.scalars(
            query.order_by(
                PurchaseRequisition.requisition_date.desc(),
                PurchaseRequisition.requisition_number.desc(),
                PurchaseRequisition.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(total or 0)

    def responses(
        self, rows: list[PurchaseRequisition]
    ) -> list[PurchaseRequisitionResponse]:
        """Shape requisitions with their lines, reading each table once."""
        if not rows:
            return []
        lines = list(
            self._session.scalars(
                select(PurchaseRequisitionLine)
                .where(
                    PurchaseRequisitionLine.requisition_id.in_([r.id for r in rows]),
                    PurchaseRequisitionLine.is_deleted.is_(False),
                )
                .order_by(PurchaseRequisitionLine.line_number.asc())
            ).all()
        )
        products = self._products({line.product_id for line in lines})
        by_parent: dict[UUID, list[PurchaseRequisitionLine]] = defaultdict(list)
        for line in lines:
            by_parent[line.requisition_id].append(line)
        return [
            PurchaseRequisitionResponse(
                id=row.id,
                branch_id=row.branch_id,
                warehouse_id=row.warehouse_id,
                requisition_number=row.requisition_number,
                requisition_date=row.requisition_date,
                needed_by=row.needed_by,
                status=row.status,
                remarks=row.remarks,
                requested_by=row.created_by,
                approved_by=row.approved_by,
                approved_at=row.approved_at,
                cancel_reason=row.cancel_reason,
                version=row.version,
                lines=[
                    PurchaseRequisitionLineResponse(
                        id=line.id,
                        line_number=line.line_number,
                        product_id=line.product_id,
                        product_code=(
                            products[line.product_id].code
                            if line.product_id in products
                            else ""
                        ),
                        product_name=(
                            products[line.product_id].name
                            if line.product_id in products
                            else ""
                        ),
                        quantity=line.quantity,
                        vendor_id=line.vendor_id,
                        remarks=line.remarks,
                        purchase_order_id=line.purchase_order_id,
                    )
                    for line in by_parent.get(row.id, [])
                ],
            )
            for row in rows
        ]

    # -- internals ------------------------------------------------------
    def _write_lines(
        self,
        row: PurchaseRequisition,
        data: PurchaseRequisitionWrite,
        *,
        actor_id: UUID,
    ) -> None:
        """Reconcile the lines on their line number."""
        products = self._products({line.product_id for line in data.lines})
        missing = [
            str(line.product_id)
            for line in data.lines
            if line.product_id not in products
            or products[line.product_id].firm_id != row.firm_id
        ]
        if missing:
            raise ValidationError("Unknown product(s): " + ", ".join(missing) + ".")
        existing = {line.line_number: line for line in self._lines(row.id)}
        seen: set[int] = set()
        for number, line in enumerate(data.lines, start=1):
            seen.add(number)
            current = existing.get(number)
            if current is None:
                current = PurchaseRequisitionLine(
                    requisition_id=row.id,
                    firm_id=row.firm_id,
                    line_number=number,
                    created_by=actor_id,
                )
                self._session.add(current)
            current.product_id = line.product_id
            current.quantity = line.quantity
            current.vendor_id = line.vendor_id
            current.remarks = line.remarks
            current.updated_by = actor_id
        for number, stale in existing.items():
            if number not in seen:
                stale.is_deleted = True
                stale.deleted_at = utc_now()
        self._session.flush()

    def _lines(self, requisition_id: UUID) -> list[PurchaseRequisitionLine]:
        """Return a requisition's live lines in order."""
        return list(
            self._session.scalars(
                select(PurchaseRequisitionLine)
                .where(
                    PurchaseRequisitionLine.requisition_id == requisition_id,
                    PurchaseRequisitionLine.is_deleted.is_(False),
                )
                .order_by(PurchaseRequisitionLine.line_number.asc())
            ).all()
        )

    def _products(self, ids: set[UUID]) -> dict[UUID, Product]:
        """Return the named products, one read."""
        if not ids:
            return {}
        return {
            p.id: p
            for p in self._session.scalars(
                select(Product).where(
                    Product.id.in_(ids), Product.is_deleted.is_(False)
                )
            ).all()
        }

    def _move(
        self,
        requisition_id: UUID,
        from_status: str,
        to_status: str,
        firm_id: UUID,
        actor_id: UUID,
        *,
        commit: bool = True,
    ) -> PurchaseRequisition:
        """Move a requisition from one status to the next."""
        row = self.get(requisition_id, firm_id=firm_id)
        if row.status != from_status:
            raise ValidationError(
                f"Only a {from_status.lower()} requisition can be "
                f"{to_status.lower()}."
            )
        row.status = to_status
        row.updated_by = actor_id
        self._audit(f"purchase_requisition.{to_status.lower()}", row, actor_id)
        if commit:
            self._session.commit()
        return row

    def _audit(self, action: str, row: PurchaseRequisition, actor_id: UUID) -> None:
        """Write one audit row for a requisition."""
        record_audit(
            self._session,
            action=action,
            entity_type="purchase_requisition",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "requisition_number": row.requisition_number,
                "status": row.status,
            },
        )


def requisition_from_picks(
    session: Session,
    *,
    firm_id: UUID,
    branch_id: UUID,
    warehouse_id: UUID,
    lines: list[tuple[UUID, Decimal, UUID | None]],
    actor_id: UUID,
    on: date,
) -> PurchaseRequisition:
    """Raise one draft requisition from reorder picks, uncommitted."""
    return PurchaseRequisitionService(session).stage_create(
        PurchaseRequisitionWrite.model_validate(
            {
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "requisition_date": on,
                "remarks": "Raised from the reorder screen",
                "lines": [
                    {"product_id": product, "quantity": quantity, "vendor_id": vendor}
                    for product, quantity, vendor in lines
                ],
            }
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )
