"""Bring a firm's customers in from a spreadsheet, with a template to fill in.

Backlog 46. The rules every master import keeps -- check every row, write all
or nothing, match headings loosely, update by code on request -- live in
``app.common.file_import``. What is particular to customers:

* **One row is one customer with one address and one contact.** The address
  columns fill the default billing (and shipping) address and the contact
  columns the primary contact; a customer with more is finished on screen.
  On an update they change that address and that contact in place, and every
  other address and contact the customer has is left alone.
* **The opening balance is booked, as the form books it** -- to the customer's
  account and to the ledger -- so a firm with no chart of accounts is told so
  per row. ``1,200 Dr`` and ``1,200 Cr`` are read the way Tally exports them:
  Dr is owed to the firm, Cr is an advance the customer has paid.
* **A standing discount or a credit limit is a price decision**, so a file
  carrying one is held to the same ``CUSTOMER_MANAGE_SETTINGS`` as the form.
* **A 10-digit phone number is taken as Indian** and written as +91, because
  that is how every Indian export writes it and the stored form is E.164.
"""

# ruff: noqa: D102, D107

import re
from decimal import Decimal
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import file_import
from app.common.file_import import (
    Column,
    FileImporter,
    ImportIssue,
    ImportReport,
    ImportRow,
    RowReader,
    schema_issues,
)
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ApplicationError
from app.customers.models import Customer, CustomerGroup
from app.customers.schemas import CustomerCreate, CustomerUpdate
from app.customers.schemas.customer import (
    AddressType,
    CustomerAddressInput,
    CustomerContactInput,
    CustomerStatus,
    CustomerType,
)
from app.customers.services.customer_service import CustomerService

#: The template, in the order it is laid out. The headings are what the notes
#: sheet explains and what every error names.
COLUMNS: tuple[Column, ...] = (
    Column(
        "Code",
        ("customercode", "partycode", "ledgercode", "accountcode"),
        True,
        "Unique customer code: letters, digits, - and _ (made upper case).",
        "SHOP-001",
    ),
    Column(
        "Name",
        ("customername", "partyname", "ledgername", "accountname"),
        True,
        "Customer name as it prints on documents.",
        "Sri Balaji Stores",
    ),
    Column(
        "DisplayName",
        ("printname", "mailingname", "tradename"),
        False,
        "The name shown in lists; blank means the Name.",
        "",
    ),
    Column(
        "Type",
        ("customertype", "partytype"),
        False,
        "One of: "
        + ", ".join(item.value for item in CustomerType)
        + ". Blank means BUSINESS.",
        "BUSINESS",
    ),
    Column(
        "Segment",
        ("customergroup", "customersegment", "group", "customercategory"),
        False,
        "An existing customer segment, by code or name (see the Lists sheet).",
        "",
    ),
    Column(
        "GSTIN",
        ("gstnumber", "gstno", "gst", "gstinuin"),
        False,
        "GST number; unique among the firm's customers.",
        "33AAAPL1234C1Z5",
    ),
    Column(
        "PAN",
        ("pannumber", "panno", "itpan"),
        False,
        "PAN; unique among the firm's customers.",
        "AAAPL1234C",
    ),
    Column("TAN", ("tannumber",), False, "TAN, as DELA12345B.", ""),
    Column(
        "Email",
        ("emailid", "emailaddress"),
        False,
        "Email address.",
        "accounts@balaji.example",
    ),
    Column(
        "Phone",
        ("mobile", "mobileno", "mobilenumber", "phoneno", "phonenumber"),
        False,
        "Phone number; 10 digits are taken as Indian (+91).",
        "9876543210",
    ),
    Column(
        "AlternatePhone",
        ("phone2", "landline", "alternatemobile"),
        False,
        "A second phone number.",
        "",
    ),
    Column("Website", ("web", "url"), False, "Website address.", ""),
    Column(
        "CreditLimit",
        ("creditamount",),
        False,
        "Number; 0 means no limit. Setting one needs the manage customer "
        "settings permission.",
        "50000",
    ),
    Column(
        "CreditDays",
        ("paymentterms", "paymenttermsdays", "creditperiod", "creditdays"),
        False,
        "Whole number of days allowed to pay.",
        "30",
    ),
    Column(
        "DiscountPercent",
        ("standingdiscount", "discount", "discountpercentage"),
        False,
        "Standing discount, 0 to 100. Setting one needs the manage customer "
        "settings permission.",
        "",
    ),
    Column(
        "Currency",
        ("currencycode",),
        False,
        "Three-letter currency code; blank means the firm's own.",
        "INR",
    ),
    Column(
        "OpeningBalance",
        ("openingbal", "opening", "openingbalanceamount"),
        False,
        "What the customer owes on day one. A minus sign, or Cr after the "
        "figure, is an advance they have paid; Dr is owed to the firm.",
        "12500",
    ),
    Column(
        "Status",
        (),
        False,
        "One of: "
        + ", ".join(item.value for item in CustomerStatus)
        + ". Blank means ACTIVE.",
        "ACTIVE",
    ),
    Column(
        "Address1",
        ("address", "addressline1", "street", "address1"),
        False,
        "First address line. An address needs Address1, City, State and PIN.",
        "12 Market Road",
    ),
    Column("Address2", ("addressline2",), False, "Second address line.", ""),
    Column("Area", ("locality",), False, "Area or locality.", ""),
    Column("City", ("town", "cityname"), False, "City.", "Chennai"),
    Column("District", (), False, "District.", ""),
    Column("State", ("statename",), False, "State.", "Tamil Nadu"),
    Column(
        "Country",
        ("countrycode",),
        False,
        "Two-letter country code; blank means IN.",
        "IN",
    ),
    Column(
        "PIN",
        ("pincode", "postalcode", "postcode", "zip", "zipcode"),
        False,
        "PIN or postal code.",
        "600001",
    ),
    Column(
        "ContactName",
        ("contactperson", "contact"),
        False,
        "The customer's main contact person.",
        "R. Kumar",
    ),
    Column(
        "ContactMobile",
        ("contactphone", "contactmobileno"),
        False,
        "Their phone; 10 digits are taken as Indian (+91).",
        "",
    ),
    Column("ContactEmail", ("contactemailid",), False, "Their email.", ""),
    Column("ContactDesignation", ("designation",), False, "Their role.", ""),
    Column("Notes", ("remarks", "narration"), False, "Free text.", ""),
)

#: The write-schema field each heading fills, for naming a schema refusal.
_FIELD_HEADINGS: dict[str, str] = {
    "code": "Code",
    "name": "Name",
    "display_name": "DisplayName",
    "customer_type": "Type",
    "customer_group_id": "Segment",
    "gst_number": "GSTIN",
    "pan_number": "PAN",
    "tan_number": "TAN",
    "email": "Email",
    "phone": "Phone",
    "alternate_phone": "AlternatePhone",
    "website": "Website",
    "credit_limit": "CreditLimit",
    "payment_terms_days": "CreditDays",
    "default_discount_percent": "DiscountPercent",
    "currency_code": "Currency",
    "opening_balance": "OpeningBalance",
    "status": "Status",
    "notes": "Notes",
    "addresses": "Address1",
    "contacts": "ContactName",
}

_TEXT_FIELDS: dict[str, str] = {
    "DisplayName": "display_name",
    "GSTIN": "gst_number",
    "PAN": "pan_number",
    "TAN": "tan_number",
    "Website": "website",
    "Notes": "notes",
}
_ADDRESS_FIELDS: dict[str, str] = {
    "Address1": "address_line1",
    "Address2": "address_line2",
    "Area": "area",
    "City": "city",
    "District": "district",
    "State": "state",
    "Country": "country",
    "PIN": "postal_code",
}
_CONTACT_FIELDS: dict[str, str] = {
    "ContactName": "name",
    "ContactMobile": "mobile",
    "ContactEmail": "email",
    "ContactDesignation": "designation",
}
_FIELD_HEADINGS.update(
    {f"addresses.{field}": heading for heading, field in _ADDRESS_FIELDS.items()}
)
_FIELD_HEADINGS.update(
    {f"contacts.{field}": heading for heading, field in _CONTACT_FIELDS.items()}
)
_DR_CR = re.compile(r"^(?P<figure>.*?)\s*(?P<side>dr|cr)\.?$", re.IGNORECASE)


class CustomerFileImporter(FileImporter[Customer]):
    """Check a customer file row by row, and import it whole or not at all."""

    COLUMNS = COLUMNS
    NOUN = "customer"

    def __init__(
        self,
        session: Session,
        service: CustomerService,
        *,
        may_manage_settings: bool,
    ) -> None:
        super().__init__(session)
        self._service = service
        self._may_manage_settings = may_manage_settings
        self._groups: list[CustomerGroup] = []
        self._currency = "INR"

    def _prepare(self, firm_id: UUID) -> None:
        self._groups = firm_segments(self._session, firm_id)
        self._currency = (
            FirmMetadataReader(self._session).get(firm_id).currency_code or "INR"
        )

    def _stored(self, firm_id: UUID) -> dict[str, Customer]:
        return {
            customer.code: customer
            for customer in self._session.scalars(
                select(Customer).where(
                    Customer.firm_id == firm_id, Customer.is_deleted.is_(False)
                )
            ).all()
        }

    def _commit(self) -> None:
        self._service._commit_unique()

    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: Customer | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[Customer],
    ) -> None:
        issues: list[ImportIssue] = []
        values = self._values(RowReader(row, code, issues), code, current)
        if issues:
            report.issues.extend(issues)
            return
        try:
            data = (
                CustomerCreate.model_validate(values)
                if current is None
                else CustomerUpdate.model_validate(values)
            )
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _FIELD_HEADINGS))
            return
        try:
            if isinstance(data, CustomerCreate):
                self._service._assert_may_set_standing_discount(
                    [data], allowed=self._may_manage_settings
                )
                customer = self._service.stage_create(
                    data, firm_id=firm_id, actor_id=actor_id
                )
                report.to_create += 1
            elif current is not None:
                customer = self._service.stage_update(
                    current,
                    data,
                    actor_id=actor_id,
                    may_change_credit_limit=self._may_manage_settings,
                    may_change_standing_discount=self._may_manage_settings,
                )
                report.to_update += 1
        except ApplicationError as error:
            # Every guard runs before the row is written, and the opening
            # balance posting refuses before it books anything, so the session
            # is still sound and the rest of the file can be checked.
            report.issues.append(ImportIssue(row.number, code, None, error.message))
            return
        report.records.append(customer)

    def _values(
        self, reader: RowReader, code: str, current: Customer | None
    ) -> dict[str, object]:
        """Turn one row's cells into write-schema values.

        On a create a blank cell takes the schema default. On an update a blank
        cell -- or a column the file does not have -- is left out, so it leaves
        the stored value alone; the four fields the schema cannot do without
        are resent as stored, which changes nothing.
        """
        values: dict[str, object] = {"code": code}
        name = reader.text("Name")
        if name:
            values["name"] = name
        elif current is None:
            reader.fail("Name", "is required.")
        else:
            values["name"] = current.name
        kind = reader.text("Type").upper()
        values["customer_type"] = kind or (
            current.customer_type if current is not None else CustomerType.BUSINESS
        )
        currency = reader.text("Currency").upper()
        values["currency_code"] = currency or (
            current.currency_code if current is not None else self._currency
        )
        status = reader.text("Status").upper().replace(" ", "_")
        if status:
            values["status"] = status
        for heading, target in _TEXT_FIELDS.items():
            if reader.text(heading):
                values[target] = reader.text(heading)
        email = reader.email("Email")
        if email:
            values["email"] = email
        for heading, target in (
            ("Phone", "phone"),
            ("AlternatePhone", "alternate_phone"),
        ):
            phone = reader.phone(heading)
            if phone:
                values[target] = phone
        for heading, target in (
            ("CreditLimit", "credit_limit"),
            ("DiscountPercent", "default_discount_percent"),
        ):
            amount = reader.number(heading)
            if amount is not None:
                values[target] = amount
        days = reader.whole("CreditDays")
        if days is not None:
            values["payment_terms_days"] = days
        opening = self._opening_balance(reader)
        if opening is not None:
            values["opening_balance"] = opening
        segment = reader.text("Segment")
        if segment:
            group = find_segment(self._groups, segment)
            if group is None:
                reader.fail("Segment", f"'{segment}' is not one of the firm's.")
            else:
                values["customer_group_id"] = group.id
        address = self._address(reader, current)
        if address is not None:
            values["addresses"] = address
        contacts = self._contacts(reader, current)
        if contacts is not None:
            values["contacts"] = contacts
        return values

    @staticmethod
    def _opening_balance(reader: RowReader) -> Decimal | None:
        """Read the opening balance, taking Tally's Dr and Cr suffixes."""
        raw = reader.text("OpeningBalance")
        if not raw:
            return None
        matched = _DR_CR.match(raw)
        if matched is None:
            return reader.number("OpeningBalance")
        figure = matched["figure"].replace(",", "").strip()
        try:
            amount = abs(Decimal(figure))
        except ArithmeticError:
            reader.fail("OpeningBalance", f"'{raw}' is not a number.")
            return None
        return amount if matched["side"].lower() == "dr" else -amount

    def _address(
        self, reader: RowReader, current: Customer | None
    ) -> list[dict[str, object]] | None:
        """Build the address list, or None when the row names no address.

        On an update the customer's other addresses are sent back unchanged,
        because the list is replaced whole and one left out is deleted.
        """
        given = {
            target: reader.text(heading)
            for heading, target in _ADDRESS_FIELDS.items()
            if reader.text(heading)
        }
        if not given:
            return None
        stored = list(current.addresses) if current is not None else []
        target = next(
            (item for item in stored if item.is_default_billing),
            stored[0] if stored else None,
        )
        kept = [
            CustomerAddressInput.model_validate(item).model_dump(mode="python")
            for item in stored
        ]
        if target is None:
            address: dict[str, object] = {
                "address_type": AddressType.BILLING,
                "country": "IN",
                "is_default_billing": True,
                "is_default_shipping": True,
            }
            address.update(given)
            for heading, field in (
                ("Address1", "address_line1"),
                ("City", "city"),
                ("State", "state"),
                ("PIN", "postal_code"),
            ):
                if not address.get(field):
                    reader.fail(heading, "is needed for an address.")
            return [*kept, address]
        for item in kept:
            if item["id"] == target.id:
                item.update(given)
                # Typed text replaces the place the masters named, so the
                # keys are cleared rather than left to overrule it.
                for key in (
                    "country_id",
                    "state_id",
                    "district_id",
                    "city_id",
                    "postal_code_id",
                    "locality_id",
                ):
                    item[key] = None
        return kept

    def _contacts(
        self, reader: RowReader, current: Customer | None
    ) -> list[dict[str, object]] | None:
        """Build the contact list, or None when the row names no contact."""
        given: dict[str, object] = {}
        name = reader.text("ContactName")
        if name:
            given["name"] = name
        designation = reader.text("ContactDesignation")
        if designation:
            given["designation"] = designation
        mobile = reader.phone("ContactMobile")
        if mobile:
            given["mobile"] = mobile
        email = reader.email("ContactEmail")
        if email:
            given["email"] = email
        if not given and not any(reader.text(heading) for heading in _CONTACT_FIELDS):
            return None
        stored = list(current.contacts) if current is not None else []
        target = next(
            (item for item in stored if item.is_primary),
            stored[0] if stored else None,
        )
        kept = [
            CustomerContactInput.model_validate(item).model_dump(mode="python")
            for item in stored
        ]
        if target is None:
            if "name" not in given:
                reader.fail("ContactName", "is needed for a contact.")
            return [*kept, {"is_primary": True, **given}]
        for item in kept:
            if item["id"] == target.id:
                item.update(given)
        return kept


def firm_segments(session: Session, firm_id: UUID) -> list[CustomerGroup]:
    """Return the firm's live customer segments."""
    return list(
        session.scalars(
            select(CustomerGroup)
            .where(
                CustomerGroup.firm_id == firm_id,
                CustomerGroup.is_deleted.is_(False),
            )
            .order_by(CustomerGroup.code)
        ).all()
    )


def find_segment(groups: list[CustomerGroup], value: str) -> CustomerGroup | None:
    """Find a segment by code, then by name, ignoring case."""
    wanted = value.strip().lower()
    for group in groups:
        if group.code.lower() == wanted:
            return group
    for group in groups:
        if group.name.strip().lower() == wanted:
            return group
    return None


def template_workbook(session: Session, firm_id: UUID) -> bytes:
    """Build the XLSX template: the sheet to fill, the notes, and the lists."""
    groups = firm_segments(session, firm_id)
    return file_import.template_workbook(
        sheet_title="Customers",
        columns=COLUMNS,
        notes=[
            "One row is one customer, with one address and one contact; add "
            "more on the customer's screen.",
            "An opening balance is booked to the ledger, so the firm needs its "
            "chart of accounts and an open period first.",
        ],
        lists_header=["Segment code", "Segment name", "", "Type", "", "Status"],
        lists=[
            [group.code for group in groups],
            [group.name for group in groups],
            [],
            [item.value for item in CustomerType],
            [],
            [item.value for item in CustomerStatus],
        ],
    )


def template_csv() -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(COLUMNS)
