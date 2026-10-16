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
* **A Beat puts the customer on an existing route** (Swathi G5) through
  ``SalesTerritoryService.set_customers`` -- the route's own list plus this
  customer, so its other rounds and every stop number are left alone. The
  file never makes a route, and needs ``TERRITORY_ASSIGN_CUSTOMERS`` as the
  route screen does.
* **A licence goes on the firm's licence register** (``trade_licences``), the
  one home a customer's licence has, through ``TradeLicenceService``'s
  ``stage_*`` methods, and needs ``TRADE_LICENCE_MANAGE`` as that screen does.
  A number the customer already holds of that type is renewed in place; a
  new number is a new licence, and the old one stays as the record of what
  was valid when past sales were made.
"""

# ruff: noqa: D102, D107

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import get_args
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
    parse_date,
    schema_issues,
    service_issue,
)
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ApplicationError
from app.customers.gst_registration import GstRegistrationType
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
from app.sales.models import (
    SalesTerritoryNode,
    TerritoryCustomerAssignment,
    TerritoryRouteProfile,
)
from app.sales.schemas import TerritoryAssignCustomersRequest
from app.sales.services.territory_service import SalesTerritoryService
from app.salesmen.models import Salesman
from app.trade_licences.models import TradeLicence, TradeLicenceType
from app.trade_licences.schemas import LicenceHolderType, TradeLicenceWrite
from app.trade_licences.services import TradeLicenceService
from app.trade_licences.services.trade_licence_service import DEFAULT_TYPES

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
        "GST number, entered on one customer only. A shop with a ParentCode "
        "leaves it blank and takes its parent's.",
        "33AAAPL1234C1Z5",
    ),
    Column(
        "ParentCode",
        ("parentcode", "parentcustomer", "parentcustomercode", "headoffice"),
        False,
        "The code of the buyer this customer is a shop of: a customer the "
        "firm already has, or one on an earlier row of this file.",
        "",
    ),
    Column(
        "GstType",
        ("gstregistrationtype", "gsttreatment", "registrationtype"),
        False,
        "One of: "
        + ", ".join(get_args(GstRegistrationType))
        + ". Blank is read off the GSTIN: Regular with one, Unregistered without.",
        "",
    ),
    Column(
        "PAN",
        ("pannumber", "panno", "itpan"),
        False,
        "PAN. Several accounts of one company may share it.",
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
        "BoxesAndPieces",
        ("billsinboxes", "boxandpiece"),
        False,
        "Yes if the customer's bills are typed as boxes and pieces, where the "
        "firm has switched that on. Blank means No.",
        "No",
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
    Column(
        "AccountManager",
        ("salesman", "salesperson", "accountmanager", "relationshipmanager"),
        False,
        "The salesman who looks after this customer, by his code or name on "
        "the firm's list of salesmen; documents raised for the customer "
        "default to him.",
        "",
    ),
    Column(
        "Beat",
        ("route", "routecode", "beatcode", "beatname", "routename"),
        False,
        "The route (beat) the customer is called on, by its code or name on "
        "the Lists sheet. The route must already exist; the customer joins it "
        "and keeps any other route it is on. Needs the assign customers to "
        "territories permission.",
        "",
    ),
    Column(
        "LicenceType",
        ("licencetype", "licensetype"),
        False,
        "The kind of licence, by its code or name on the Lists sheet "
        "(DRUG_WHOLESALE, FSSAI ...). Needed with a LicenceNumber.",
        "",
    ),
    Column(
        "LicenceNumber",
        (
            "licenceno",
            "licenseno",
            "licensenumber",
            "druglicence",
            "druglicense",
            "dlno",
            "dlnumber",
        ),
        False,
        "The customer's licence number, kept on the firm's licence register. "
        "Needs the manage trade licences permission.",
        "",
    ),
    Column(
        "LicenceExpiry",
        ("licencevalidto", "licensevalidto", "licenseexpiry", "dlexpiry"),
        False,
        "The day the licence runs out, as dd-mm-yyyy. Needed for a type that "
        "expires.",
        "",
    ),
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
    "parent_customer_id": "ParentCode",
    "gst_registration_type": "GstType",
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
    "box_and_piece_entry": "BoxesAndPieces",
    "salesman_id": "AccountManager",
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


#: The licence write-schema fields, for naming a register refusal.
_LICENCE_HEADINGS: dict[str, str] = {
    "licence_number": "LicenceNumber",
    "licence_type_id": "LicenceType",
    "valid_to": "LicenceExpiry",
}


def _named(issues: list[ImportIssue], heading: str) -> list[ImportIssue]:
    """Give the issues that name no column the one the cells came from."""
    return [
        (
            issue
            if issue.column is not None
            else ImportIssue(issue.row, issue.code, heading, issue.message)
        )
        for issue in issues
    ]


@dataclass(frozen=True)
class _LicenceCells:
    """One row's licence, read and matched but not yet recorded."""

    licence_type: TradeLicenceType
    number: str
    valid_to: date | None


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
        may_assign_routes: bool = False,
        may_record_licences: bool = False,
    ) -> None:
        super().__init__(session)
        self._service = service
        self._may_manage_settings = may_manage_settings
        self._may_assign_routes = may_assign_routes
        self._may_record_licences = may_record_licences
        self._territories = SalesTerritoryService(session)
        self._licences = TradeLicenceService(session)
        self._groups: list[CustomerGroup] = []
        self._currency = "INR"
        self._salesmen: list[tuple[UUID, str | None, str]] = []
        self._routes: list[SalesTerritoryNode] = []
        self._licence_types: list[TradeLicenceType] | None = None
        self._firm_id: UUID | None = None

    def _prepare(self, firm_id: UUID) -> None:
        self._firm_id = firm_id
        self._routes = firm_routes(self._session, firm_id)
        self._licence_types = None
        self._groups = firm_segments(self._session, firm_id)
        reader = FirmMetadataReader(self._session)
        self._currency = reader.get(firm_id).currency_code or "INR"
        self._salesmen = list(
            self._session.execute(
                select(Salesman.id, Salesman.code, Salesman.name).where(
                    Salesman.firm_id == firm_id,
                    Salesman.is_deleted.is_(False),
                    Salesman.is_active.is_(True),
                )
            ).tuples()
        )

    def _member(self, reader: RowReader) -> UUID | None:
        """Find the row's account manager on the firm's salesman list.

        By the salesman's code, then his name (P2 step 2). Nothing else is
        looked up: a member's email or full name is refused like any other
        stranger, since the list is the authority on who may be named.
        """
        given = reader.text("AccountManager")
        if not given:
            return None
        wanted = given.casefold()
        for entry_id, code, name in self._salesmen:
            if (code or "").casefold() == wanted or name.casefold() == wanted:
                return entry_id
        reader.fail(
            "AccountManager", f"'{given}' is not on the firm's list of salesmen."
        )
        return None

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
        reader = RowReader(row, code, issues)
        values = self._values(reader, code, current)
        route = self._route(reader)
        licence = self._licence(reader)
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
                self._service._assert_may_set_price_terms(
                    [data], allowed=self._may_manage_settings
                )
                customer = self._service.stage_create(
                    data, firm_id=firm_id, actor_id=actor_id
                )
            elif current is not None:
                customer = self._service.stage_update(
                    current,
                    data,
                    actor_id=actor_id,
                    may_change_credit_limit=self._may_manage_settings,
                    may_change_standing_discount=self._may_manage_settings,
                )
        except ApplicationError as error:
            # Every guard runs before the row is written, and the opening
            # balance posting refuses before it books anything, so the session
            # is still sound and the rest of the file can be checked.
            report.issues.append(service_issue(error, row, code, _FIELD_HEADINGS))
            return
        attached = route is None or self._join_route(
            route, customer, row=row, code=code, actor_id=actor_id, report=report
        )
        if not attached:
            return
        if licence is not None and not self._record_licence(
            licence, customer, row=row, code=code, actor_id=actor_id, report=report
        ):
            return
        if current is None:
            report.to_create += 1
        else:
            report.to_update += 1
        report.records.append(customer)

    def _route(self, reader: RowReader) -> SalesTerritoryNode | None:
        """Find the row's Beat among the firm's routes, by code then name.

        Only a node with a route profile is a route; an area is refused
        rather than having shops hung on it, and the file never makes one.
        """
        given = reader.text("Beat").strip()
        if not given:
            return None
        if not self._may_assign_routes:
            reader.fail(
                "Beat",
                "Putting a customer on a route needs the assign customers to "
                "territories permission (TERRITORY_ASSIGN_CUSTOMERS).",
            )
            return None
        wanted = given.casefold()
        for node in self._routes:
            if node.code.casefold() == wanted:
                return node
        named = [
            node for node in self._routes if node.name.strip().casefold() == wanted
        ]
        if len(named) == 1:
            return named[0]
        if named:
            reader.fail("Beat", f"'{given}' names more than one route; give its code.")
        else:
            reader.fail(
                "Beat",
                f"'{given}' is not one of the firm's routes; add the route "
                "first, or name one on the Lists sheet.",
            )
        return None

    def _licence(self, reader: RowReader) -> _LicenceCells | None:
        """Read the row's licence cells and match the type; None if blank."""
        number = reader.text("LicenceNumber").strip()
        kind = reader.text("LicenceType").strip()
        expiry_text = reader.text("LicenceExpiry").strip()
        if not number:
            if kind or expiry_text:
                reader.fail(
                    "LicenceNumber", "is needed with a LicenceType or LicenceExpiry."
                )
            return None
        if not self._may_record_licences:
            reader.fail(
                "LicenceNumber",
                "Recording a customer's licence needs the manage trade "
                "licences permission (TRADE_LICENCE_MANAGE).",
            )
            return None
        valid_to: date | None = None
        if expiry_text:
            valid_to = parse_date(expiry_text)
            if valid_to is None:
                reader.fail(
                    "LicenceExpiry",
                    f"'{expiry_text}' is not a date; write it as dd-mm-yyyy.",
                )
        if not kind:
            reader.fail(
                "LicenceType",
                "is needed with a LicenceNumber; name one of the firm's "
                "licence types (see the Lists sheet).",
            )
            return None
        licence_type = find_licence_type(self._types(), kind)
        if licence_type is None:
            reader.fail(
                "LicenceType",
                f"'{kind}' is not one of the firm's active licence types (see "
                "the Lists sheet).",
            )
            return None
        return _LicenceCells(licence_type, number.upper(), valid_to)

    def _types(self) -> list[TradeLicenceType]:
        """Return the firm's active licence types, seeding the usual ones.

        Seeded only where the firm has none at all, as the licence screen
        does on its first read; a check rolls the seeding back with the rest.
        """
        if self._firm_id is None:
            return []
        if self._licence_types is None:
            if not firm_licence_types(self._session, self._firm_id, active=False):
                self._licences.ensure_default_types(self._firm_id, None)
            self._licence_types = firm_licence_types(self._session, self._firm_id)
        return self._licence_types

    def _join_route(
        self,
        route: SalesTerritoryNode,
        customer: Customer,
        *,
        row: ImportRow,
        code: str,
        actor_id: UUID,
        report: ImportReport[Customer],
    ) -> bool:
        """Put the customer on the route, keeping everyone already on it.

        The route's list is sent back whole with this customer added, the
        plain shape the route screen's picker sends, so every stop number
        stays where it was. A customer already on the route is left alone.
        """
        on_route = list(
            self._session.scalars(
                select(TerritoryCustomerAssignment.customer_id).where(
                    TerritoryCustomerAssignment.territory_id == route.id,
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                )
            ).all()
        )
        if customer.id in on_route:
            return True
        try:
            self._territories.set_customers(
                route.id,
                TerritoryAssignCustomersRequest(customer_ids=[*on_route, customer.id]),
                firm_scope=customer.firm_id,
                actor_id=actor_id,
                commit=False,
            )
        except PydanticValidationError as error:
            report.issues.extend(_named(schema_issues(error, row, code, {}), "Beat"))
            return False
        except ApplicationError as error:
            report.issues.append(ImportIssue(row.number, code, "Beat", error.message))
            return False
        return True

    def _record_licence(
        self,
        licence: _LicenceCells,
        customer: Customer,
        *,
        row: ImportRow,
        code: str,
        actor_id: UUID,
        report: ImportReport[Customer],
    ) -> bool:
        """Record the licence on the register, or renew the one already held."""
        held = self._session.scalar(
            select(TradeLicence).where(
                TradeLicence.firm_id == customer.firm_id,
                TradeLicence.customer_id == customer.id,
                TradeLicence.licence_type_id == licence.licence_type.id,
                TradeLicence.licence_number == licence.number,
                TradeLicence.is_deleted.is_(False),
            )
        )
        if held is not None and licence.valid_to in (None, held.valid_to):
            return True
        if held is None and licence.valid_to is None and licence.licence_type.expires:
            report.issues.append(
                ImportIssue(
                    row.number,
                    code,
                    "LicenceExpiry",
                    f"is needed: a {licence.licence_type.name} runs out, and an "
                    "expiry nobody wrote down is one nobody is warned about.",
                )
            )
            return False
        try:
            data = TradeLicenceWrite(
                licence_type_id=licence.licence_type.id,
                holder_type=LicenceHolderType.CUSTOMER,
                customer_id=customer.id,
                licence_number=licence.number,
                issued_by=None if held is None else held.issued_by,
                valid_from=None if held is None else held.valid_from,
                valid_to=licence.valid_to,
                premises=None if held is None else held.premises,
                remarks=None if held is None else held.remarks,
            )
            if held is None:
                self._licences.stage_create_licence(
                    data, firm_id=customer.firm_id, actor_id=actor_id
                )
            else:
                self._licences.stage_update_licence(
                    held.id, data, firm_id=customer.firm_id, actor_id=actor_id
                )
        except PydanticValidationError as error:
            report.issues.extend(
                _named(
                    schema_issues(error, row, code, _LICENCE_HEADINGS),
                    "LicenceExpiry",
                )
            )
            return False
        except ApplicationError as error:
            report.issues.append(
                ImportIssue(row.number, code, "LicenceNumber", error.message)
            )
            return False
        return True

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
        boxes = reader.flag("BoxesAndPieces")
        if boxes is not None:
            values["box_and_piece_entry"] = boxes
        for heading, target in _TEXT_FIELDS.items():
            if reader.text(heading):
                values[target] = reader.text(heading)
        gst_type = reader.text("GstType").upper().replace(" ", "_")
        if gst_type:
            values["gst_registration_type"] = gst_type
        parent_code = reader.text("ParentCode").upper()
        if parent_code:
            # Read from the store at this row, so a parent staged by an
            # earlier row of the same file is found (backlog 125).
            parent_id = self._session.scalar(
                select(Customer.id).where(
                    Customer.firm_id == self._firm_id,
                    Customer.is_deleted.is_(False),
                    Customer.code == parent_code,
                )
            )
            if parent_id is None:
                reader.fail(
                    "ParentCode",
                    f"'{parent_code}' is not a customer of the firm, nor on an "
                    "earlier row of this file.",
                )
            else:
                values["parent_customer_id"] = parent_id
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
        manager = self._member(reader)
        if manager is not None:
            values["salesman_id"] = manager
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


def firm_routes(session: Session, firm_id: UUID) -> list[SalesTerritoryNode]:
    """Return the firm's live routes -- nodes with a route profile -- by code."""
    return list(
        session.scalars(
            select(SalesTerritoryNode)
            .join(
                TerritoryRouteProfile,
                TerritoryRouteProfile.territory_id == SalesTerritoryNode.id,
            )
            .where(
                SalesTerritoryNode.firm_id == firm_id,
                SalesTerritoryNode.is_deleted.is_(False),
                TerritoryRouteProfile.is_deleted.is_(False),
            )
            .order_by(SalesTerritoryNode.code)
        ).all()
    )


def firm_licence_types(
    session: Session, firm_id: UUID, *, active: bool = True
) -> list[TradeLicenceType]:
    """Return the firm's live licence types by code, only active ones if asked."""
    query = select(TradeLicenceType).where(
        TradeLicenceType.firm_id == firm_id,
        TradeLicenceType.is_deleted.is_(False),
    )
    if active:
        query = query.where(TradeLicenceType.is_active.is_(True))
    return list(session.scalars(query.order_by(TradeLicenceType.code)).all())


def find_licence_type(
    types: list[TradeLicenceType], value: str
) -> TradeLicenceType | None:
    """Find a licence type by code, then by name, ignoring case."""
    wanted = value.strip().casefold()
    for item in types:
        if item.code.casefold() == wanted:
            return item
    for item in types:
        if item.name.strip().casefold() == wanted:
            return item
    return None


def template_workbook(session: Session, firm_id: UUID) -> bytes:
    """Build the XLSX template: the sheet to fill, the notes, and the lists."""
    groups = firm_segments(session, firm_id)
    routes = firm_routes(session, firm_id)
    # A firm that has never opened the licence screen has no types yet; the
    # import seeds the usual ones, so the template lists those.
    licence_types = [
        (item.code, item.name) for item in firm_licence_types(session, firm_id)
    ] or [(code, name) for code, name, _, _ in DEFAULT_TYPES]
    return file_import.template_workbook(
        sheet_title="Customers",
        columns=COLUMNS,
        notes=[
            "One row is one customer, with one address and one contact; add "
            "more on the customer's screen.",
            "An opening balance is booked to the ledger, so the firm needs its "
            "chart of accounts and an open period first.",
            "A Beat names a route the firm already has; the file does not "
            "make routes.",
            "A licence goes on the firm's licence register: give its type, "
            "number and, for a type that runs out, its expiry.",
        ],
        lists_header=[
            "Segment code",
            "Segment name",
            "",
            "Type",
            "",
            "Status",
            "",
            "Route code",
            "Route name",
            "",
            "Licence type code",
            "Licence type",
        ],
        lists=[
            [group.code for group in groups],
            [group.name for group in groups],
            [],
            [item.value for item in CustomerType],
            [],
            [item.value for item in CustomerStatus],
            [],
            [route.code for route in routes],
            [route.name for route in routes],
            [],
            [code for code, _ in licence_types],
            [name for _, name in licence_types],
        ],
    )


def template_csv() -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(COLUMNS)
