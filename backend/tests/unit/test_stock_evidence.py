"""Photos and documents kept with stock movements and count sheets (STK-9, A64).

A write-off, an adjustment, a transfer or a count is a decision somebody may
later have to justify; the photo or signed slip is kept beside it. A transfer's
files are kept on its outbound leg and read from either.
"""

# ruff: noqa: D103

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.core.exceptions import ResourceNotFoundError
from app.firms.models import Firm
from app.inventory.models import InventoryRecord, StockAttachment
from app.inventory.schemas import (
    InventoryAdjustmentCreate,
    PhysicalCountCreate,
    StockAttachmentWrite,
    StockTransferCreate,
    StockWriteOffCreate,
)
from app.inventory.services import InventoryService, PhysicalCountService
from app.inventory.services.stock_evidence import StockEvidenceService
from app.products.models import Product
from tests.unit.test_opening_stock_import_file import _ON
from tests.unit.test_stock_valuation import _stocked

pytestmark = pytest.mark.typed_document_numbers

_PHOTO = StockAttachmentWrite(
    file_name="crushed.jpg",
    mime_type="image/jpeg",
    file_path="C:/evidence/crushed.jpg",
    caption=" Crushed cartons, bay 4 ",
)


def _rice(session: Session, firm: Firm) -> InventoryRecord:
    """Return the rice stock row in the MAIN warehouse."""
    rice = session.scalar(
        select(Product).where(Product.firm_id == firm.id, Product.code == "RICE")
    )
    assert rice is not None
    rows = list(
        session.scalars(
            select(InventoryRecord).where(
                InventoryRecord.firm_id == firm.id,
                InventoryRecord.product_id == rice.id,
            )
        )
    )
    return max(rows, key=lambda row: row.current_quantity)


def test_a_write_off_keeps_its_photo() -> None:
    session, firm = _stocked()
    record = _rice(session, firm)

    movement = InventoryService(session).write_off_stock(
        StockWriteOffCreate(
            branch_id=record.branch_id,
            warehouse_id=record.warehouse_id,
            product_id=record.product_id,
            reason="DAMAGE",  # type: ignore[arg-type]
            quantity=Decimal("1"),
            transaction_date=_ON + timedelta(days=2),
            attachments=[_PHOTO],
        ),
        firm_scope=firm.id,
        actor_id=firm.id,
    )

    files = StockEvidenceService(session).for_movement(movement.id, firm_id=firm.id)
    assert [(row.file_name, row.caption) for row in files] == [
        ("crushed.jpg", "Crushed cartons, bay 4")
    ]
    assert files[0].created_by == firm.id


def test_an_adjustment_keeps_its_files_and_none_is_written_without_them() -> None:
    session, firm = _stocked()
    record = _rice(session, firm)
    service = InventoryService(session)
    data = InventoryAdjustmentCreate(
        branch_id=record.branch_id,
        warehouse_id=record.warehouse_id,
        product_id=record.product_id,
        quantity=Decimal("-1"),
        transaction_date=_ON + timedelta(days=2),
    )

    bare = service.create_adjustment(data, firm_scope=firm.id, actor_id=firm.id)
    backed = service.create_adjustment(
        data.model_copy(update={"attachments": [_PHOTO, _PHOTO]}),
        firm_scope=firm.id,
        actor_id=firm.id,
    )

    evidence = StockEvidenceService(session)
    assert evidence.for_movement(bare.id, firm_id=firm.id) == []
    assert len(evidence.for_movement(backed.id, firm_id=firm.id)) == 2


def test_a_transfers_files_are_read_from_either_leg() -> None:
    session, firm = _stocked()
    record = _rice(session, firm)
    east = next(
        row
        for row in session.scalars(
            select(InventoryRecord).where(
                InventoryRecord.firm_id == firm.id,
                InventoryRecord.product_id == record.product_id,
            )
        )
        if row.warehouse_id != record.warehouse_id
    )

    outbound, inbound = InventoryService(session).transfer_stock(
        StockTransferCreate(
            branch_id=record.branch_id,
            from_warehouse_id=record.warehouse_id,
            to_warehouse_id=east.warehouse_id,
            product_id=record.product_id,
            quantity=Decimal("2"),
            transaction_date=_ON + timedelta(days=2),
            attachments=[_PHOTO],
        ),
        firm_scope=firm.id,
        actor_id=firm.id,
    )
    evidence = StockEvidenceService(session)
    # A slip added later from the inbound line lands on the same leg.
    evidence.attach_to_movement(
        inbound.id,
        [StockAttachmentWrite(file_name="slip.pdf", file_path="C:/e/slip.pdf")],
        firm_id=firm.id,
        actor_id=firm.id,
    )

    from_out = evidence.for_movement(outbound.id, firm_id=firm.id)
    from_in = evidence.for_movement(inbound.id, firm_id=firm.id)
    assert [row.file_name for row in from_out] == ["crushed.jpg", "slip.pdf"]
    assert [row.id for row in from_in] == [row.id for row in from_out]
    assert {row.inventory_transaction_id for row in from_out} == {outbound.id}


def test_a_count_sheet_keeps_files_and_removing_one_leaves_a_trail() -> None:
    session, firm = _stocked()
    record = _rice(session, firm)
    count = PhysicalCountService(session).create(
        PhysicalCountCreate(
            branch_id=record.branch_id,
            warehouse_id=record.warehouse_id,
            count_date=_ON + timedelta(days=2),
        ),
        firm_id=firm.id,
        actor_id=firm.id,
    )
    session.commit()
    evidence = StockEvidenceService(session)

    [row] = evidence.attach_to_count(
        count.id, [_PHOTO], firm_id=firm.id, actor_id=firm.id
    )
    assert [item.id for item in evidence.for_count(count.id, firm_id=firm.id)] == [
        row.id
    ]

    evidence.remove(row.id, firm_id=firm.id, actor_id=firm.id)

    assert evidence.for_count(count.id, firm_id=firm.id) == []
    kept = session.get(StockAttachment, row.id)
    assert kept is not None and kept.is_deleted
    actions = set(
        session.scalars(
            select(AuditLog.action).where(AuditLog.entity_id == count.id)
        )
    )
    assert {"inventory.evidence_attached", "inventory.evidence_removed"} <= actions


def test_another_firms_movement_is_not_found() -> None:
    session, firm = _stocked()
    record = _rice(session, firm)
    movement = InventoryService(session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=record.branch_id,
            warehouse_id=record.warehouse_id,
            product_id=record.product_id,
            quantity=Decimal("1"),
            transaction_date=_ON + timedelta(days=2),
        ),
        firm_scope=firm.id,
        actor_id=firm.id,
    )
    stranger = record.branch_id  # any id that is not a firm

    with pytest.raises(ResourceNotFoundError):
        StockEvidenceService(session).attach_to_movement(
            movement.id, [_PHOTO], firm_id=stranger, actor_id=firm.id
        )
