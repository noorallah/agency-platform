"""Where an outward supply is made, and so whether it crosses a state border.

GST is levied as central plus state tax on a supply made within one state and
as integrated tax on one made between states (IGST Act, sections 7 and 8), and
which of the two a supply is turns on its **place of supply** against the
supplier's location (section 10). The rule engine cannot see either -- a rule
reads ``transaction_type`` -- so every outward document names its supply
``SALES_INTERSTATE`` when the two states differ, and the firm's interstate rules
(``INTERSTATE_GST_*``, conditioned on that name) switch the line to IGST.

Before this existed nothing sent ``SALES_INTERSTATE`` at all, so every sale to
another state was charged CGST and SGST (D-CMP-1): a return the portal rejects,
and an e-invoice registration refused for good.

The two states are read as GST state codes -- the two digits a GSTIN starts
with -- because that is what a return and an e-invoice file:

- **The supplier** is the firm's own GSTIN. A branch registered for GST in a
  state of its own supplies from there; branches carry no GSTIN of their own,
  so that branch's state is read from its address.
- **The buyer** is the buyer's GSTIN where it has one. An unregistered buyer has
  none, so the address the invoice is addressed to decides it -- the billing
  address, then the default billing one, then any live address, the same order
  ``SalesInvoiceService._place_of_supply`` prints -- so the printed place of
  supply and the tax charged cannot name different states. An address outside
  India is a supply to another country, which section 7(5)(a) makes
  inter-state.

Where either state cannot be told, the supply is treated as the document's own
type, which is what every document did before; nothing is guessed.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch
from app.common.firm_metadata import FirmMetadataReader
from app.customers.models import Customer, CustomerAddress
from app.sales.models.territory import GeoState

#: The transaction type the firm's interstate rules are conditioned on.
SALES_INTERSTATE = "SALES_INTERSTATE"

#: The code a GST return and an e-invoice give a place outside India.
FOREIGN_STATE_CODE = "96"

#: GST state codes by the two-letter abbreviation ``geo_states`` holds. The
#: numbers are the ones a GSTIN starts with (CBIC's state code list); 26 is the
#: merged Dadra and Nagar Haveli and Daman and Diu, 37 the post-2014 Andhra
#: Pradesh and 38 Ladakh.
_CODES_BY_ABBREVIATION: dict[str, str] = {
    "JK": "01",
    "HP": "02",
    "PB": "03",
    "CH": "04",
    "UK": "05",
    "UT": "05",
    "HR": "06",
    "DL": "07",
    "RJ": "08",
    "UP": "09",
    "BR": "10",
    "SK": "11",
    "AR": "12",
    "NL": "13",
    "MN": "14",
    "MZ": "15",
    "TR": "16",
    "ML": "17",
    "AS": "18",
    "WB": "19",
    "JH": "20",
    "OD": "21",
    "OR": "21",
    "CG": "22",
    "CT": "22",
    "MP": "23",
    "GJ": "24",
    "DH": "26",
    "DD": "26",
    "DN": "26",
    "MH": "27",
    "KA": "29",
    "GA": "30",
    "LD": "31",
    "KL": "32",
    "TN": "33",
    "PY": "34",
    "AN": "35",
    "TS": "36",
    "TG": "36",
    "AP": "37",
    "LA": "38",
}

#: The same codes by state name, lower-cased, for an address whose state is
#: free text with no geography key behind it.
_CODES_BY_NAME: dict[str, str] = {
    "jammu and kashmir": "01",
    "himachal pradesh": "02",
    "punjab": "03",
    "chandigarh": "04",
    "uttarakhand": "05",
    "haryana": "06",
    "delhi": "07",
    "rajasthan": "08",
    "uttar pradesh": "09",
    "bihar": "10",
    "sikkim": "11",
    "arunachal pradesh": "12",
    "nagaland": "13",
    "manipur": "14",
    "mizoram": "15",
    "tripura": "16",
    "meghalaya": "17",
    "assam": "18",
    "west bengal": "19",
    "jharkhand": "20",
    "odisha": "21",
    "orissa": "21",
    "chhattisgarh": "22",
    "madhya pradesh": "23",
    "gujarat": "24",
    "dadra and nagar haveli and daman and diu": "26",
    "daman and diu": "26",
    "dadra and nagar haveli": "26",
    "maharashtra": "27",
    "karnataka": "29",
    "goa": "30",
    "lakshadweep": "31",
    "kerala": "32",
    "tamil nadu": "33",
    "puducherry": "34",
    "pondicherry": "34",
    "andaman and nicobar islands": "35",
    "telangana": "36",
    "andhra pradesh": "37",
    "ladakh": "38",
}


def gst_state_code(value: str | None) -> str | None:
    """Return the GST state code a state is named by, however it is written.

    Accepts the two digits themselves, a GSTIN, the two-letter abbreviation or
    the state's name.

    Args:
        value: A state code, GSTIN, abbreviation or name.

    Returns:
        The two-digit code, or None when the value names no Indian state.

    """
    text = (value or "").strip()
    if not text:
        return None
    if len(text) >= 2 and text[:2].isdigit():
        return text[:2]
    upper = text.upper()
    if upper in _CODES_BY_ABBREVIATION:
        return _CODES_BY_ABBREVIATION[upper]
    normalised = " ".join(text.lower().replace("&", "and").split())
    return _CODES_BY_NAME.get(normalised)


class SupplyPlaceResolver:
    """Decide whether an outward supply crosses a state border.

    One per service instance: the firm's GSTIN is a platform fact, read through
    ``FirmMetadataReader`` and cached there, so a fifty-line invoice asks the
    platform once rather than fifty times.
    """

    def __init__(self, session: Session) -> None:
        """Bind to the caller's session."""
        self._session = session
        self._firms = FirmMetadataReader(session)

    def outward_transaction_type(
        self,
        document_type: str,
        *,
        firm_id: UUID,
        branch_id: UUID | None,
        customer_id: UUID | None,
    ) -> str:
        """Return the transaction type an outward supply is priced as.

        Args:
            document_type: The document's own type -- ``SALES_INVOICE``,
                ``SALES_ORDER`` and so on -- used for a supply within one state.
            firm_id: The supplying firm.
            branch_id: The branch the document is raised at.
            customer_id: The buyer.

        Returns:
            ``SALES_INTERSTATE`` when the supplier's and the buyer's states are
            both known and differ, otherwise ``document_type``.

        """
        if self.is_interstate(
            firm_id=firm_id, branch_id=branch_id, customer_id=customer_id
        ):
            return SALES_INTERSTATE
        return document_type

    def is_interstate(
        self, *, firm_id: UUID, branch_id: UUID | None, customer_id: UUID | None
    ) -> bool:
        """Return whether the supply is made in a state other than the supplier's."""
        seller = self.supplier_state(firm_id=firm_id, branch_id=branch_id)
        buyer = self.buyer_state(customer_id)
        return seller is not None and buyer is not None and seller != buyer

    def supplier_state(self, *, firm_id: UUID, branch_id: UUID | None) -> str | None:
        """Return the GST state code the supply is made from."""
        branch = self._session.get(Branch, branch_id) if branch_id is not None else None
        if (
            branch is not None
            and not branch.is_deleted
            and branch.gst_registration
            and branch.state_id is not None
        ):
            own = self._geo_state_code(branch.state_id)
            if own is not None:
                return own
        firm = gst_state_code(self._firms.get(firm_id).gst_number)
        if firm is not None:
            return firm
        if branch is not None and branch.state_id is not None:
            return self._geo_state_code(branch.state_id)
        return None

    def buyer_state(self, customer_id: UUID | None) -> str | None:
        """Return the GST state code of the buyer's place of supply."""
        if customer_id is None:
            return None
        customer = self._session.get(Customer, customer_id)
        if customer is None:
            return None
        registered = gst_state_code(customer.gst_number)
        if registered is not None:
            return registered
        address = self._addressed_to(customer)
        if address is None:
            return None
        country = (address.country or "").strip().upper()
        if country and country != "IN":
            return FOREIGN_STATE_CODE
        if address.state_id is not None:
            keyed = self._geo_state_code(address.state_id)
            if keyed is not None:
                return keyed
        return gst_state_code(address.state)

    @staticmethod
    def _addressed_to(customer: Customer) -> CustomerAddress | None:
        """Return the address an invoice to this buyer is addressed to."""
        live = [
            address
            for address in (customer.addresses or [])
            if not address.is_deleted and (address.state or address.state_id)
        ]
        for preferred in (
            lambda address: address.address_type == "BILLING",
            lambda address: bool(address.is_default_billing),
            lambda address: True,
        ):
            for address in live:
                if preferred(address):
                    return address
        return None

    def _geo_state_code(self, state_id: UUID) -> str | None:
        """Return the GST state code of a ``geo_states`` row."""
        row = self._session.execute(
            select(GeoState.code, GeoState.name).where(GeoState.id == state_id)
        ).first()
        if row is None:
            return None
        return gst_state_code(row[0]) or gst_state_code(row[1])
