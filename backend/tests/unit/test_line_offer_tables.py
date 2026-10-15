"""Offers chosen on the bill line, step 1: the tables, columns and permission.

L7 of ``docs/CUSTOMER_BUILD_TASKS.md``, step 1 of section 6 of
``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md``. Nothing reads these yet;
what is proved here is that they exist in the shape section 3.9 states, start
empty and false, carry no key to ``firms``, and that the permission reaches
every role that makes a sales bill.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.identity.system_seed import (
    PERMISSION_GROUPS,
    ROLE_PERMISSION_CODES,
    SYSTEM_PERMISSION_CODES,
)
from app.promotions.models.promotion import Promotion
from app.quotation.models import SalesQuotationLine, SalesQuotationOffer
from app.sales_order.models import SalesOrderLine, SalesOrderOffer

_TABLES = {
    "sales_order_offers": ("sales_order_id", "sales_order_line_id"),
    "sales_quotation_offers": ("sales_quotation_id", "sales_quotation_line_id"),
}


@pytest.mark.parametrize("table", sorted(_TABLES))
def test_the_offer_table_has_the_columns_of_section_3_9(table: str) -> None:
    """Each table carries the design's columns and no key to ``firms``."""
    columns = Base.metadata.tables[table].c
    document, line = _TABLES[table]
    for name in (
        "firm_id",
        document,
        line,
        "sequence",
        "source",
        "promotion_id",
        "promotion_group_id",
        "price_list_id",
        "code",
        "name",
        "state",
        "chosen",
        "discount_amount",
        "free_quantity",
        "part_share",
    ):
        assert name in columns, name
    assert not columns["firm_id"].foreign_keys
    assert not columns[document].nullable
    assert columns[line].nullable
    keys = {
        key.column.table.name: key.ondelete
        for column in columns
        for key in column.foreign_keys
    }
    assert keys[document.removesuffix("_id") + "s"] == "CASCADE"
    assert keys["promotions"] == "RESTRICT"
    assert keys["price_lists"] == "RESTRICT"


def test_the_new_flags_start_false() -> None:
    """``allow_part_share`` and ``offer_choice_made`` default to off."""
    for column in (
        Promotion.__table__.c.allow_part_share,
        SalesOrderLine.__table__.c.offer_choice_made,
        SalesQuotationLine.__table__.c.offer_choice_made,
        SalesOrderOffer.__table__.c.chosen,
        SalesQuotationOffer.__table__.c.part_share,
    ):
        assert not column.nullable
        assert column.server_default is not None


def test_a_row_can_be_written_and_read_back() -> None:
    """A row needs only what the design says it needs; the rest defaults."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    assert {"sales_order_offers", "sales_quotation_offers"} <= set(
        inspect(engine).get_table_names()
    )
    with Session(engine) as session:
        session.execute(
            Base.metadata.tables["sales_order_offers"]
            .insert()
            .values(
                id=uuid4(),
                firm_id=uuid4(),
                sales_order_id=uuid4(),
                source="customer",
                code="CUSTOMER",
                name="Standing rate",
                state="APPLIED",
            )
        )
        row = session.query(SalesOrderOffer).one()
        assert row.sales_order_line_id is None
        assert row.sequence == 0
        assert row.chosen is False
        assert row.part_share is False
        assert row.discount_amount == Decimal("0")
        assert row.free_quantity == Decimal("0")


def test_choosing_an_offer_is_seeded_to_every_role_that_makes_a_sales_bill() -> None:
    """``SALES_OFFER_CHOOSE`` is a sales code held by each bill-making role."""
    assert "SALES_OFFER_CHOOSE" in PERMISSION_GROUPS["sales"]
    assert "SALES_OFFER_CHOOSE" in SYSTEM_PERMISSION_CODES
    makers = [
        role
        for role, codes in ROLE_PERMISSION_CODES.items()
        if codes & {"SALES_ORDER_CREATE", "SALES_INVOICE_CREATE"}
    ]
    assert {"SALES_MANAGER", "SALES_EXECUTIVE", "BILLING_EXECUTIVE"} <= set(makers)
    for role in makers:
        assert "SALES_OFFER_CHOOSE" in ROLE_PERMISSION_CODES[role], role
