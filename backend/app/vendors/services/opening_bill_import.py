"""Suppliers' opening bills from a file: the payable side of D-GOLIVE-1."""

from typing import Any
from uuid import UUID

from app.common.opening_bill_import import OpeningBillFileImporter, parties_by_code
from app.vendors.models import Vendor, VendorOpeningBill
from app.vendors.schemas.opening_bill import VendorOpeningBillWrite
from app.vendors.services.opening_bill_service import VendorOpeningBillService


class VendorOpeningBillFileImporter(
    OpeningBillFileImporter[Vendor, VendorOpeningBillWrite, VendorOpeningBill]
):
    """What the firm owed each supplier on its first day here, bill by bill."""

    PARTY = "supplier"
    CODE_ALIASES = ("suppliercode", "vendorcode", "creditorcode", "partyno")

    def _parties(self, firm_id: UUID) -> dict[str, Vendor]:
        return parties_by_code(self._session, Vendor, firm_id)

    def _write_model(self, values: dict[str, Any]) -> VendorOpeningBillWrite:
        return VendorOpeningBillWrite(**values)

    def _stage(
        self,
        party: Vendor,
        write: VendorOpeningBillWrite,
        firm_id: UUID,
        actor_id: UUID,
    ) -> VendorOpeningBill:
        return VendorOpeningBillService(self._session)._stage(
            party, write, firm_id=firm_id, actor_id=actor_id
        )
