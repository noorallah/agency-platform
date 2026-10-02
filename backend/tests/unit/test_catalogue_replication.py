"""Features and modules written at runtime reach every store (MST-7, A69).

The profile catalogue already reached every store under one id (backlog 17);
the features and modules a profile enables did not, so a feature made by the
platform administrator existed in the caller's store alone and every other
store refused it by name when a profile tried to enable it. These drive the
real routes over the multi-store harness of ``test_profile_replication``.
"""

from uuid import UUID

from fastapi import Response
from sqlalchemy import select

from app.business.api.router import (
    create_feature,
    create_module,
    delete_feature,
    delete_module,
    update_feature,
)
from app.business.models import BusinessFeature, BusinessModule
from app.business.schemas import (
    BusinessFeatureCreate,
    BusinessFeatureUpdate,
    BusinessModuleCreate,
)
from app.common.audit.models import AuditLog
from tests.unit.test_profile_replication import _World


def _feature_in(world: _World, store: str, feature_id: UUID) -> BusinessFeature | None:
    """Read a feature straight out of one store."""
    with world.stores[store]() as db:
        return db.get(BusinessFeature, feature_id)


def test_a_new_feature_reaches_every_store_under_one_id() -> None:
    """Created everywhere with the caller's id, each store auditing its own."""
    world = _World()
    response = create_feature(
        BusinessFeatureCreate(code="cold_chain", name="Cold chain"),
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )
    feature_id = response.data.id
    for store in ("whole", "shared", "pharm"):
        copy = _feature_in(world, store, feature_id)
        assert copy is not None and copy.code == "COLD_CHAIN", store
    outcomes = {item.store: item for item in response.data.stores}
    assert outcomes["shared/firm (FOOD01, FOOD02)"].detail == "created"
    assert outcomes["NEW01"].status == "FAILED"
    assert response.data.warning is not None
    with world.stores["pharm"]() as db:
        assert (
            db.scalar(select(AuditLog.action).where(AuditLog.entity_id == feature_id))
            == "business_feature.created"
        )


def test_a_change_and_a_delete_follow_the_feature() -> None:
    """An edit updates every copy; a delete removes every copy."""
    world = _World()
    feature_id = create_feature(
        BusinessFeatureCreate(code="COLD_CHAIN", name="Cold chain"),
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    ).data.id

    updated = update_feature(
        feature_id,
        BusinessFeatureUpdate(code="COLD_CHAIN", name="Cold chain logistics"),
        world.principal,
        Response(),
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )
    assert {
        item.detail for item in updated.data.stores if item.status == "WRITTEN"
    } == {"updated"}
    copy = _feature_in(world, "pharm", feature_id)
    assert copy is not None and copy.name == "Cold chain logistics"

    removed = delete_feature(
        feature_id,
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )
    assert {item.detail for item in removed.data if item.status == "WRITTEN"} == {
        "deleted"
    }
    copy = _feature_in(world, "shared", feature_id)
    assert copy is not None and copy.is_deleted


def test_a_store_holding_the_code_under_another_id_is_reported() -> None:
    """Two ids for one code is the drift this prevents: named, not overwritten."""
    world = _World()
    with world.stores["pharm"]() as db:
        db.add(BusinessFeature(code="COLD_CHAIN", name="Theirs", is_implemented=True))
        db.commit()
    response = create_feature(
        BusinessFeatureCreate(code="COLD_CHAIN", name="Cold chain"),
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )
    outcomes = {item.store: item for item in response.data.stores}
    assert outcomes["pharm/firm (PHARM01)"].status == "FAILED"
    assert outcomes["shared/firm (FOOD01, FOOD02)"].status == "WRITTEN"


def test_a_new_module_reaches_every_store_and_leaves_with_its_delete() -> None:
    """Modules follow the same path as features."""
    world = _World()
    response = create_module(
        BusinessModuleCreate(code="COLD_STORE", name="Cold store", ui_route="cold"),
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )
    module_id = response.data.id
    for store in ("shared", "pharm"):
        with world.stores[store]() as db:
            copy = db.get(BusinessModule, module_id)
            assert copy is not None and copy.ui_route == "cold", store

    delete_module(
        module_id,
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )
    with world.stores["pharm"]() as db:
        copy = db.get(BusinessModule, module_id)
        assert copy is not None and copy.is_deleted
