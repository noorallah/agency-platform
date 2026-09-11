"""An exported branch or warehouse file can be imported back.

Found in manual testing on 2026-09-11, plan item 5.9: the branch export
wrote six columns and the importer read eleven, with the two they shared
spelled differently, so an exported file was neither a backup nor a
template. Both exports now write exactly the importer's columns, and these
tests prove it the only way that means anything -- by reading the export
back through the write schema and the service.

The warehouse file names its branch by **code**. It used to demand the
branch's id, which nothing on a screen shows anybody, so the sample file
could only write "<id of an existing branch>" and was refused on import.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.api.router import (
    BRANCH_EXPORT_COLUMNS,
    WAREHOUSE_EXPORT_COLUMNS,
    branches_csv,
    warehouses_csv,
)
from app.branches.schemas import BranchCreate, WarehouseCreate, WarehouseUpdate
from app.branches.services import BranchWarehouseService
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.firms.models import Firm


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session) -> Firm:
    row = Firm(
        name="Export Firm",
        code="EXP01",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _rows(text: str) -> list[dict[str, str]]:
    """Read a CSV the way the desktop importer does: blanks are omitted."""
    return [
        {key: value for key, value in row.items() if value}
        for row in csv.DictReader(io.StringIO(text))
    ]


def test_a_branch_export_carries_every_import_column_and_reads_back() -> None:
    """Every column the importer reads is written, and the row re-validates."""
    session = _session()
    firm = _firm(session)
    actor = uuid4()
    service = BranchWarehouseService(session)
    service.create_branch(
        BranchCreate.model_validate(
            {
                "code": "BR_NORTH",
                "name": "North Branch",
                "display_name": "North",
                "description": "Northern region branch",
                "email": "north@example.com",
                "phone": "+912212345678",
                "mobile": "+919876543210",
                "address_line1": "12 Ring Road",
                "address_line2": "Sector 4",
                "currency_code": "INR",
                "status": "ACTIVE",
            }
        ),
        firm_id=firm.id,
        actor_id=actor,
    )

    text = branches_csv(session, firm_id=firm.id, search=None)

    assert text.splitlines()[0] == ",".join(BRANCH_EXPORT_COLUMNS)
    (row,) = _rows(text)
    assert row == {
        "code": "BR_NORTH",
        "name": "North Branch",
        "display_name": "North",
        "description": "Northern region branch",
        "email": "north@example.com",
        "phone": "+912212345678",
        "mobile": "+919876543210",
        "address_line1": "12 Ring Road",
        "address_line2": "Sector 4",
        "currency_code": "INR",
        "status": "ACTIVE",
    }
    # The round trip: the exported row is a valid create, code aside.
    again = BranchCreate.model_validate({**row, "code": "BR_NORTH_2"})
    assert again.address_line2 == "Sector 4"
    assert again.mobile == "+919876543210"


def test_a_warehouse_export_names_its_branch_by_code_and_reads_back() -> None:
    """The warehouse twin: exported with the branch's code, imported by it."""
    session = _session()
    firm = _firm(session)
    actor = uuid4()
    service = BranchWarehouseService(session)
    branch = service.create_branch(
        BranchCreate.model_validate({"code": "HO", "name": "Head Office"}),
        firm_id=firm.id,
        actor_id=actor,
    )
    service.create_warehouse(
        WarehouseCreate.model_validate(
            {
                "branch_id": branch.id,
                "code": "WH_NORTH",
                "name": "North Warehouse",
                "display_name": "North WH",
                "address_line1": "12 Ring Road",
                "capacity": "5000",
                "capacity_unit": "SQFT",
            }
        ),
        firm_id=firm.id,
        actor_id=actor,
    )

    text = warehouses_csv(session, firm_id=firm.id, search=None)

    assert text.splitlines()[0] == ",".join(WAREHOUSE_EXPORT_COLUMNS)
    assert "branch_id" not in WAREHOUSE_EXPORT_COLUMNS
    (row,) = _rows(text)
    assert row["branch_code"] == "HO"
    assert row["display_name"] == "North WH"
    assert row["address_line1"] == "12 Ring Road"
    assert "address_line2" not in row, "an empty cell is blank, not 'None'"

    # The round trip, all the way into the store: the exported row, with a
    # new code, creates a warehouse under the same branch.
    again = service.import_warehouses(
        [WarehouseCreate.model_validate({**row, "code": "WH_NORTH_2"})],
        firm_id=firm.id,
        actor_id=actor,
    )
    assert again[0].branch_id == branch.id
    assert str(again[0].capacity) == "5000.000"
    assert again[0].capacity_unit == "SQFT"


def test_a_warehouse_naming_an_unknown_branch_code_is_refused_by_name() -> None:
    """The person correcting the file needs to know which cell was wrong."""
    session = _session()
    firm = _firm(session)
    service = BranchWarehouseService(session)

    with pytest.raises(ValidationError, match="No branch with code NOWHERE"):
        service.create_warehouse(
            WarehouseCreate.model_validate(
                {"branch_code": "nowhere", "code": "WH1", "name": "Lost"}
            ),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
    # Lower-case in the file, upper-case in the refusal: codes are normalised
    # on the way in, so the message names the code as the store spells it.


def test_a_new_warehouse_must_name_its_branch_one_way_or_the_other() -> None:
    """Neither id nor code is a schema refusal, before any store is touched."""
    with pytest.raises(PydanticValidationError, match="branch_id or branch_code"):
        WarehouseCreate.model_validate({"code": "WH1", "name": "Nowhere"})


def test_an_update_that_names_no_branch_keeps_the_one_it_has() -> None:
    """A rename must not need the branch restated -- and may move it by code."""
    session = _session()
    firm = _firm(session)
    actor = uuid4()
    service = BranchWarehouseService(session)
    first = service.create_branch(
        BranchCreate.model_validate({"code": "HO", "name": "Head Office"}),
        firm_id=firm.id,
        actor_id=actor,
    )
    second = service.create_branch(
        BranchCreate.model_validate({"code": "DEPOT", "name": "Depot"}),
        firm_id=firm.id,
        actor_id=actor,
    )
    warehouse = service.create_warehouse(
        WarehouseCreate.model_validate(
            {"branch_code": "HO", "code": "WH1", "name": "Main"}
        ),
        firm_id=firm.id,
        actor_id=actor,
    )
    assert warehouse.branch_id == first.id

    renamed = service.update_warehouse(
        warehouse.id,
        WarehouseUpdate(code="WH1", name="Main Store"),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert renamed.branch_id == first.id

    moved = service.update_warehouse(
        warehouse.id,
        WarehouseUpdate(code="WH1", name="Main Store", branch_code="DEPOT"),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert moved.branch_id == second.id
