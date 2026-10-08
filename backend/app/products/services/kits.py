"""Kits and combo packs (STK-15, decision A134).

A gift pack is a product of type ``BUNDLE`` with a list of what goes into
one: two soaps and a towel. It is stocked and sold as itself -- the order
reserves it, the note ships it, the bill shows it, a return brings it back --
and it is *made* from its components by a repack (STK-4), which moves their
value into it, so its cost is theirs:

* *Assemble* consumes the components for a number of kits and produces them;
  *Disassemble* is the same repack the other way.
* A note that ships more kits than are assembled assembles the shortfall
  from components first, in the same transaction, so selling a kit takes its
  components off the shelf -- the way Zoho composite items and ERPNext
  product bundles leave the components' stock behind them.

A kit's components are ordinary products; a kit is not a component of
another kit.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.inventory.models import InventoryRecord
from app.products.models import Product
from app.products.models.kit import ProductKitComponent

KIT_TYPE = "BUNDLE"
ZERO = Decimal("0")


class KitComponentWrite(BaseModel):
    """One component and how many go into one kit."""

    model_config = ConfigDict(extra="forbid")

    component_product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class KitComponentsWrite(BaseModel):
    """A kit's whole component list, replacing what is there."""

    model_config = ConfigDict(extra="forbid")

    components: list[KitComponentWrite] = Field(default_factory=list, max_length=50)


class KitComponentResponse(BaseModel):
    """One component as listed."""

    model_config = ConfigDict(extra="forbid")

    component_product_id: UUID
    component_code: str
    component_name: str
    quantity: Decimal


class KitAssemblyWrite(BaseModel):
    """Assemble or break a number of kits in one warehouse."""

    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
    warehouse_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    on: date | None = None
    remarks: str | None = Field(default=None, max_length=1000)


class KitService:
    """Keep a kit's component list, and assemble or break kits."""

    def __init__(self, session: Session) -> None:
        """Bind to the caller's session."""
        self._session = session

    # ---- the list ------------------------------------------------------

    def components(self, kit_id: UUID, *, firm_id: UUID) -> list[ProductKitComponent]:
        """Return a kit's live components."""
        self._kit(kit_id, firm_id=firm_id, require_type=False)
        return self._components(kit_id)

    def responses(self, rows: list[ProductKitComponent]) -> list[KitComponentResponse]:
        """Shape components with their product's code and name."""
        names = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_([row.component_product_id for row in rows] or [None])
                )
            ).all()
        }
        return [
            KitComponentResponse(
                component_product_id=row.component_product_id,
                component_code=getattr(names.get(row.component_product_id), "code", ""),
                component_name=getattr(names.get(row.component_product_id), "name", ""),
                quantity=row.quantity,
            )
            for row in rows
        ]

    def replace(
        self,
        kit_id: UUID,
        data: KitComponentsWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[ProductKitComponent]:
        """Replace a kit's component list; commit.

        Raises:
            ValidationError: If the product is not a kit, a component is the
                kit itself, another kit, tracked by serial number, not the
                firm's, or named twice.

        """
        kit = self._kit(kit_id, firm_id=firm_id)
        ids = [item.component_product_id for item in data.components]
        if len(set(ids)) != len(ids):
            raise ValidationError("A component is named twice.")
        if kit.id in ids:
            raise ValidationError("A kit is not a component of itself.")
        found = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_(ids or [None]),
                    Product.firm_id == firm_id,
                    Product.is_deleted.is_(False),
                )
            ).all()
        }
        if set(ids) - set(found):
            raise ValidationError("A component is not one of this firm's products.")
        nested = [p.code for p in found.values() if p.product_type == KIT_TYPE]
        if nested:
            raise ValidationError(
                "A kit is not a component of another kit: " + ", ".join(nested) + "."
            )
        units = sorted(p.code for p in found.values() if p.track_serial)
        if units:
            # Assembling moves a quantity and names no unit, so a part
            # tracked by serial number would leave its units behind
            # (D-STK-52).
            raise ValidationError(
                "A part tracked by serial number cannot go into a kit, "
                "because assembling names no units: " + ", ".join(units) + "."
            )
        now = utc_now()
        for old in self._components(kit.id):
            old.is_deleted = True
            old.deleted_at = now
            old.deleted_by = actor_id
        self._session.flush()
        for item in data.components:
            self._session.add(
                ProductKitComponent(
                    firm_id=firm_id,
                    kit_product_id=kit.id,
                    component_product_id=item.component_product_id,
                    quantity=item.quantity,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        record_audit(
            self._session,
            action="product.kit_components_replaced",
            entity_type="product",
            entity_id=kit.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "components": [
                    {
                        "product_id": str(i.component_product_id),
                        "quantity": str(i.quantity),
                    }
                    for i in data.components
                ]
            },
        )
        self._session.commit()
        return self._components(kit.id)

    # ---- assembling ----------------------------------------------------

    def assemble(
        self,
        kit_id: UUID,
        data: KitAssemblyWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        disassemble: bool = False,
    ) -> object:
        """Make (or break) kits by a repack; commit. Returns the repack."""
        repack = self.stage_assembly(
            kit_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            quantity=data.quantity,
            on=data.on or firm_today(self._session, firm_id),
            remarks=data.remarks,
            firm_id=firm_id,
            actor_id=actor_id,
            disassemble=disassemble,
        )
        self._session.commit()
        return repack

    def stage_assembly(
        self,
        kit_id: UUID,
        *,
        branch_id: UUID,
        warehouse_id: UUID,
        quantity: Decimal,
        on: date,
        remarks: str | None,
        firm_id: UUID,
        actor_id: UUID,
        disassemble: bool = False,
    ) -> object:
        """Post the repack that makes or breaks kits, without committing.

        Raises:
            ValidationError: If the kit has no components, or the warehouse
                does not hold enough of what is consumed -- naming it.

        """
        from app.inventory.services.repacking import RepackService, RepackWrite

        kit = self._kit(kit_id, firm_id=firm_id)
        parts = self._components(kit.id)
        if not parts:
            raise ValidationError(f"{kit.code} has no components to assemble from.")
        needs = (
            [(kit.id, kit.code, quantity)]
            if disassemble
            else [
                (
                    part.component_product_id,
                    self._code(part.component_product_id),
                    Decimal(str(part.quantity)) * quantity,
                )
                for part in parts
            ]
        )
        for product_id, code, needed in needs:
            held = self.on_hand(
                firm_id=firm_id,
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
            )
            if held < needed:
                raise ValidationError(
                    f"{code}: {held} available, {needed} needed to "
                    + ("break" if disassemble else "assemble")
                    + f" {quantity} of {kit.code}."
                )
        kit_line = {"product_id": kit.id, "quantity": quantity}
        part_lines = [
            {
                "product_id": part.component_product_id,
                "quantity": Decimal(str(part.quantity)) * quantity,
            }
            for part in parts
        ]
        return RepackService(self._session).stage_post(
            RepackWrite.model_validate(
                {
                    "repack_date": on,
                    "branch_id": branch_id,
                    "warehouse_id": warehouse_id,
                    "remarks": remarks
                    or (
                        f"{'Disassembled' if disassemble else 'Assembled'} "
                        f"{quantity} of {kit.code}"
                    ),
                    "lines": (
                        [{"kind": "CONSUME", **kit_line}]
                        + [{"kind": "PRODUCE", **line} for line in part_lines]
                        if disassemble
                        else [{"kind": "CONSUME", **line} for line in part_lines]
                        + [{"kind": "PRODUCE", **kit_line}]
                    ),
                }
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )

    def assemble_for_dispatch(
        self,
        *,
        firm_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        product_id: UUID,
        shortfall: Decimal,
        on: date,
        reference: str,
        actor_id: UUID,
    ) -> bool:
        """Assemble the kits a note ships beyond what is assembled; stages.

        Returns False, doing nothing, for a product that is not a kit with
        components -- the note's own stock check then speaks for it.
        """
        if shortfall <= ZERO:
            return False
        product = self._session.get(Product, product_id)
        if (
            product is None
            or product.product_type != KIT_TYPE
            or not self._components(product_id)
        ):
            return False
        self.stage_assembly(
            product_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            quantity=shortfall,
            on=on,
            remarks=f"Assembled {shortfall} of {product.code} for {reference}",
            firm_id=firm_id,
            actor_id=actor_id,
        )
        return True

    def on_hand(
        self,
        *,
        firm_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        product_id: UUID,
    ) -> Decimal:
        """Return what a warehouse holds free of a product, all batches."""
        held = self._session.scalar(
            select(
                func.coalesce(func.sum(InventoryRecord.available_quantity), 0)
            ).where(
                InventoryRecord.firm_id == firm_id,
                InventoryRecord.branch_id == branch_id,
                InventoryRecord.warehouse_id == warehouse_id,
                InventoryRecord.product_id == product_id,
                InventoryRecord.is_deleted.is_(False),
            )
        )
        return Decimal(str(held or 0))

    # ---- helpers -------------------------------------------------------

    def _kit(
        self, kit_id: UUID, *, firm_id: UUID, require_type: bool = True
    ) -> Product:
        """Return one of the firm's kit products."""
        product = self._session.get(Product, kit_id)
        if product is None or product.is_deleted or product.firm_id != firm_id:
            raise ResourceNotFoundError("Product not found.")
        if require_type and product.product_type != KIT_TYPE:
            raise ValidationError(
                f"{product.code} is not a kit; set its type to Bundle first."
            )
        return product

    def _components(self, kit_id: UUID) -> list[ProductKitComponent]:
        """Return a kit's live components in the order they were listed."""
        return list(
            self._session.scalars(
                select(ProductKitComponent)
                .where(
                    ProductKitComponent.kit_product_id == kit_id,
                    ProductKitComponent.is_deleted.is_(False),
                )
                .order_by(ProductKitComponent.created_at, ProductKitComponent.id)
            ).all()
        )

    def _code(self, product_id: UUID) -> str:
        """Return a product's code."""
        return str(
            self._session.scalar(select(Product.code).where(Product.id == product_id))
            or ""
        )
