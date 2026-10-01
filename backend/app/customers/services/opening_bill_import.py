"""Customers' opening bills from a file: the receivable side of D-GOLIVE-1."""

from typing import Any
from uuid import UUID

from app.common.opening_bill_import import OpeningBillFileImporter, parties_by_code
from app.core.utils.money import quantize_ledger
from app.customers.models import Customer, CustomerOpeningBill
from app.customers.schemas.opening_bill import CustomerOpeningBillWrite
from app.customers.services.opening_bill_service import CustomerOpeningBillService


class CustomerOpeningBillFileImporter(
    OpeningBillFileImporter[Customer, CustomerOpeningBillWrite, CustomerOpeningBill]
):
    """What each customer owed the firm on its first day here, bill by bill."""

    PARTY = "customer"
    CODE_ALIASES = ("customercode", "clientcode", "debtorcode", "partyno")
    NOTES = (
        "A customer with an opening balance figure on its screen is refused: "
        "the balance would count twice. Set it to 0 first. The Lists sheet "
        "names only the customers without one.",
    )

    def _parties(self, firm_id: UUID) -> dict[str, Customer]:
        return parties_by_code(self._session, Customer, firm_id)

    def _refusal(self, party: Customer) -> str | None:
        if party.opening_balance == 0:
            return None
        return (
            f"{party.code} carries an opening balance of "
            f"{quantize_ledger(party.opening_balance)}. Enter it either as one "
            "figure on the customer or bill by bill, not both -- set the "
            "customer's opening balance to 0 first."
        )

    def _write_model(self, values: dict[str, Any]) -> CustomerOpeningBillWrite:
        return CustomerOpeningBillWrite(**values)

    def _stage(
        self,
        party: Customer,
        write: CustomerOpeningBillWrite,
        firm_id: UUID,
        actor_id: UUID,
    ) -> CustomerOpeningBill:
        return CustomerOpeningBillService(self._session)._stage(
            party, write, firm_id=firm_id, actor_id=actor_id
        )
