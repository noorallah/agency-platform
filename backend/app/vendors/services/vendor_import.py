"""Bring a firm's suppliers in from a spreadsheet, with a template to fill in.

Backlog 46. The rules every master import keeps -- check every row, write all
or nothing, match headings loosely, update by code on request -- live in
``app.common.file_import``. What is particular to suppliers:

* **One row is one supplier with one address, one contact and one bank
  account.** On an update each changes the primary row in place, and every
  other address, contact and account the supplier has is left alone.
* **An address is placed in the geography masters, never stored as text** --
  a supplier's address holds only the keys. The PIN is looked up first, then
  the city, then the state; one the masters do not hold is reported, never
  guessed.
* **A bank account is where payments go**, so a file carrying one is held to
  ``VENDOR_MANAGE_BANK_DETAILS``, as the form is.
* **What a supplier was owed at cutover is not here.** It is brought in bill
  by bill as supplier opening bills, which are their own import.
"""

# ruff: noqa: D102, D107

from collections.abc import Sequence
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import ColumnElement, func, select
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
from app.core.exceptions import ApplicationError
from app.sales.models.territory import (
    GeoCity,
    GeoCountry,
    GeoDistrict,
    GeoPostalCode,
    GeoState,
)
from app.vendors.models import Vendor, VendorCategory, VendorType
from app.vendors.schemas import VendorCreate, VendorUpdate
from app.vendors.schemas.vendor import (
    AddressType,
    VendorAddressInput,
    VendorBankInput,
    VendorContactInput,
    VendorStatus,
)
from app.vendors.services.vendor_service import VendorService

#: The template, in the order it is laid out. The headings are what the notes
#: sheet explains and what every error names.
COLUMNS: tuple[Column, ...] = (
    Column(
        "Code",
        ("vendorcode", "suppliercode", "partycode", "ledgercode", "accountcode"),
        True,
        "Unique supplier code: letters, digits, - and _ (made upper case).",
        "SUP-001",
    ),
    Column(
        "Name",
        ("vendorname", "suppliername", "partyname", "ledgername", "accountname"),
        True,
        "Supplier name as it prints on documents.",
        "Acme Distributors",
    ),
    Column(
        "LegalName",
        ("registeredname", "companyname"),
        False,
        "The registered name, where it differs.",
        "",
    ),
    Column(
        "DisplayName",
        ("printname", "mailingname", "tradename"),
        False,
        "The name shown in lists; blank means the Name.",
        "",
    ),
    Column(
        "Category",
        ("vendorcategory", "suppliercategory", "group", "suppliergroup"),
        False,
        "An existing supplier category, by code or name (see the Lists sheet).",
        "",
    ),
    Column(
        "Type",
        ("vendortype", "suppliertype"),
        False,
        "An existing supplier type, by code or name (see the Lists sheet).",
        "",
    ),
    Column(
        "GSTIN",
        ("gstnumber", "gstno", "gst", "gstinuin"),
        False,
        "GST number; unique among the firm's suppliers. Marks them registered.",
        "33AAACA1234A1Z5",
    ),
    Column("PAN", ("pannumber", "panno", "itpan"), False, "PAN.", "AAACA1234A"),
    Column(
        "LicenseNumber",
        ("licenceno", "licenseno", "druglicense", "druglicence", "dlno"),
        False,
        "Licence number.",
        "",
    ),
    Column(
        "RegistrationNumber",
        ("regno", "cin", "registrationno"),
        False,
        "Company or firm registration number.",
        "",
    ),
    Column("Email", ("emailid", "emailaddress"), False, "Email address.", ""),
    Column(
        "Phone",
        ("phoneno", "phonenumber", "landline", "telephone"),
        False,
        "Phone; 10 digits are taken as Indian (+91).",
        "",
    ),
    Column(
        "Mobile",
        ("mobileno", "mobilenumber", "cell"),
        False,
        "Mobile; 10 digits are taken as Indian (+91).",
        "9876543210",
    ),
    Column("Website", ("web", "url"), False, "Website address.", ""),
    Column(
        "Status",
        (),
        False,
        "One of: "
        + ", ".join(item.value for item in VendorStatus)
        + ". Blank means ACTIVE.",
        "ACTIVE",
    ),
    Column("Remarks", ("notes", "narration"), False, "Free text.", ""),
    Column(
        "Address1",
        ("address", "addressline1", "street"),
        False,
        "First address line; needed for an address.",
        "14 Industrial Estate",
    ),
    Column("Address2", ("addressline2",), False, "Second address line.", ""),
    Column(
        "City",
        ("town", "cityname"),
        False,
        "City, as the geography masters name it.",
        "",
    ),
    Column(
        "State",
        ("statename",),
        False,
        "State, by name or code, as the geography masters hold it.",
        "",
    ),
    Column(
        "PIN",
        ("pincode", "postalcode", "postcode", "zip", "zipcode"),
        False,
        "PIN code; places the address by itself when the masters hold it.",
        "",
    ),
    Column(
        "Country",
        ("countrycode",),
        False,
        "Country, by code or name; read only when no state is given.",
        "",
    ),
    Column(
        "ContactName",
        ("contactperson", "contact"),
        False,
        "The supplier's main contact person.",
        "S. Rao",
    ),
    Column("ContactDesignation", ("designation",), False, "Their role.", ""),
    Column(
        "ContactMobile",
        ("contactphone", "contactmobileno"),
        False,
        "Their mobile; 10 digits are taken as Indian (+91).",
        "",
    ),
    Column("ContactEmail", ("contactemailid",), False, "Their email.", ""),
    Column(
        "BankName",
        ("bank",),
        False,
        "Bank name. An account needs BankName, AccountName and "
        "AccountNumber, and the manage vendor bank details permission.",
        "",
    ),
    Column(
        "AccountName",
        ("accountholder", "beneficiaryname", "accountholdername"),
        False,
        "Name on the account.",
        "",
    ),
    Column(
        "AccountNumber",
        ("accountno", "bankaccount", "bankaccountnumber", "acno"),
        False,
        "Account number, as text so leading zeros stay.",
        "",
    ),
    Column("IFSC", ("ifsccode",), False, "IFSC code.", ""),
    Column("UPI", ("upiid", "vpa"), False, "UPI id.", ""),
)

#: The write-schema field each heading fills, for naming a schema refusal.
_FIELD_HEADINGS: dict[str, str] = {
    "code": "Code",
    "name": "Name",
    "legal_name": "LegalName",
    "display_name": "DisplayName",
    "category_id": "Category",
    "type_id": "Type",
    "gstin": "GSTIN",
    "pan": "PAN",
    "license_number": "LicenseNumber",
    "registration_number": "RegistrationNumber",
    "email": "Email",
    "phone": "Phone",
    "mobile": "Mobile",
    "website": "Website",
    "status": "Status",
    "remarks": "Remarks",
    "addresses": "Address1",
    "addresses.address_line1": "Address1",
    "addresses.address_line2": "Address2",
    "contacts": "ContactName",
    "contacts.name": "ContactName",
    "contacts.designation": "ContactDesignation",
    "contacts.mobile": "ContactMobile",
    "contacts.email": "ContactEmail",
    "banking": "BankName",
    "banking.bank_name": "BankName",
    "banking.account_name": "AccountName",
    "banking.account_number": "AccountNumber",
    "banking.ifsc": "IFSC",
    "banking.upi_id": "UPI",
}

_TEXT_FIELDS: dict[str, str] = {
    "LegalName": "legal_name",
    "DisplayName": "display_name",
    "GSTIN": "gstin",
    "PAN": "pan",
    "LicenseNumber": "license_number",
    "RegistrationNumber": "registration_number",
    "Website": "website",
    "Remarks": "remarks",
}
_ADDRESS_HEADINGS = ("Address1", "Address2", "City", "State", "PIN", "Country")
_BANK_FIELDS: dict[str, str] = {
    "BankName": "bank_name",
    "AccountName": "account_name",
    "AccountNumber": "account_number",
    "IFSC": "ifsc",
    "UPI": "upi_id",
}
GeoMaster = GeoCountry | GeoState | GeoDistrict | GeoCity | GeoPostalCode
_PLACE_KEYS = (
    "country_id",
    "state_id",
    "district_id",
    "city_id",
    "postal_code_id",
    "locality_id",
)


def _live(model: type[GeoMaster]) -> ColumnElement[bool]:
    """Return the filter that keeps a master's usable rows."""
    return model.is_deleted.is_(False) & model.is_active.is_(True)


class _Places:
    """Place a typed address in the geography masters, or say it cannot."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(self, reader: RowReader) -> dict[str, object]:
        """Return the geography keys the row's City, State and PIN name.

        The PIN places an address by itself; a city narrows a PIN several
        towns share; a state is enough on its own. Each column that names a
        place the masters do not hold is reported against that column.
        """
        keys: dict[str, object] = {}
        state = self._state(reader) if reader.text("State") else None
        if state is not None:
            keys.update(state_id=state.id, country_id=state.country_id)
        elif not reader.text("State") and reader.text("Country"):
            country = self._country(reader)
            if country is not None:
                keys["country_id"] = country.id
        city = self._city(reader, state) if reader.text("City") else None
        if city is not None:
            self._climb_from_city(city, keys)
        if reader.text("PIN"):
            postal = self._postal(reader, city, state)
            if postal is not None:
                keys["postal_code_id"] = postal.id
                if city is None:
                    found = self._session.get(GeoCity, postal.city_id)
                    if found is not None:
                        self._climb_from_city(found, keys)
        return keys

    def _climb_from_city(self, city: GeoCity, keys: dict[str, object]) -> None:
        """Fill the district, state and country a city sits under."""
        keys["city_id"] = city.id
        district = self._session.get(GeoDistrict, city.district_id)
        if district is None:
            return
        keys["district_id"] = district.id
        state = self._session.get(GeoState, district.state_id)
        if state is not None:
            keys["state_id"] = state.id
            keys["country_id"] = state.country_id

    def _country(self, reader: RowReader) -> GeoCountry | None:
        wanted = reader.text("Country").strip().lower()
        found = self._session.scalars(
            select(GeoCountry).where(
                _live(GeoCountry),
                (func.lower(GeoCountry.code) == wanted)
                | (func.lower(GeoCountry.iso2) == wanted)
                | (func.lower(GeoCountry.iso3) == wanted)
                | (func.lower(GeoCountry.name) == wanted),
            )
        ).first()
        if found is None:
            reader.fail("Country", self._missing(reader.text("Country")))
        return found

    def _state(self, reader: RowReader) -> GeoState | None:
        wanted = reader.text("State").strip().lower()
        found = self._session.scalars(
            select(GeoState).where(
                _live(GeoState),
                (func.lower(GeoState.name) == wanted)
                | (func.lower(GeoState.code) == wanted),
            )
        ).all()
        if len(found) != 1:
            reader.fail(
                "State",
                (
                    self._missing(reader.text("State"))
                    if not found
                    else f"'{reader.text('State')}' names more than one state."
                ),
            )
            return None
        return found[0]

    def _city(self, reader: RowReader, state: GeoState | None) -> GeoCity | None:
        wanted = reader.text("City").strip().lower()
        statement = select(GeoCity).where(
            _live(GeoCity), func.lower(GeoCity.name) == wanted
        )
        if state is not None:
            statement = statement.join(
                GeoDistrict, GeoDistrict.id == GeoCity.district_id
            ).where(GeoDistrict.state_id == state.id)
        found = self._session.scalars(statement).all()
        if len(found) != 1:
            reader.fail(
                "City",
                (
                    self._missing(reader.text("City"))
                    if not found
                    else f"'{reader.text('City')}' is in more than one state; "
                    "give the State as well."
                ),
            )
            return None
        return found[0]

    def _postal(
        self, reader: RowReader, city: GeoCity | None, state: GeoState | None
    ) -> GeoPostalCode | None:
        wanted = reader.text("PIN").replace(" ", "")
        statement = select(GeoPostalCode).where(
            _live(GeoPostalCode), GeoPostalCode.postal_code == wanted
        )
        if city is not None:
            statement = statement.where(GeoPostalCode.city_id == city.id)
        elif state is not None:
            statement = (
                statement.join(GeoCity, GeoCity.id == GeoPostalCode.city_id)
                .join(GeoDistrict, GeoDistrict.id == GeoCity.district_id)
                .where(GeoDistrict.state_id == state.id)
            )
        found = self._session.scalars(statement).all()
        if not found:
            reader.fail("PIN", self._missing(reader.text("PIN")))
            return None
        if len(found) > 1 and city is None:
            reader.fail(
                "PIN",
                f"'{reader.text('PIN')}' serves more than one city; give the "
                "City as well.",
            )
            return None
        return found[0]

    @staticmethod
    def _missing(value: str) -> str:
        """Say a place is not in the masters, and where to add it."""
        return (
            f"'{value}' is not in the geography masters. Add it under Setup > "
            "Geography, or leave the column blank."
        )


class VendorFileImporter(FileImporter[Vendor]):
    """Check a supplier file row by row, and import it whole or not at all."""

    COLUMNS = COLUMNS
    NOUN = "supplier"

    def __init__(
        self,
        session: Session,
        service: VendorService,
        *,
        may_manage_bank_details: bool,
    ) -> None:
        super().__init__(session)
        self._service = service
        self._may_manage_bank = may_manage_bank_details
        self._categories: list[VendorCategory] = []
        self._types: list[VendorType] = []
        self._places = _Places(session)

    def _prepare(self, firm_id: UUID) -> None:
        self._categories, self._types = firm_masters(self._session, firm_id)

    def _stored(self, firm_id: UUID) -> dict[str, Vendor]:
        return {
            vendor.code: vendor
            for vendor in self._session.scalars(
                select(Vendor).where(
                    Vendor.firm_id == firm_id, Vendor.is_deleted.is_(False)
                )
            ).all()
        }

    def _commit(self) -> None:
        self._service._commit_unique()

    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: Vendor | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[Vendor],
    ) -> None:
        issues: list[ImportIssue] = []
        values = self._values(RowReader(row, code, issues), code, current)
        if issues:
            report.issues.extend(issues)
            return
        try:
            data = (
                VendorCreate.model_validate(values)
                if current is None
                else VendorUpdate.model_validate(values)
            )
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _FIELD_HEADINGS))
            return
        try:
            if isinstance(data, VendorCreate):
                self._service._assert_may_set_bank_details(
                    [data], allowed=self._may_manage_bank
                )
                vendor = self._service.stage_create(
                    data, firm_id=firm_id, actor_id=actor_id
                )
                report.to_create += 1
            elif current is not None:
                vendor = self._service.stage_update(
                    current,
                    data,
                    actor_id=actor_id,
                    may_manage_bank_details=self._may_manage_bank,
                    # Whoever may manage the accounts may see them; whoever
                    # may not is refused below rather than served a blank.
                    may_view_bank_details=True,
                )
                report.to_update += 1
        except ApplicationError as error:
            # Every guard runs before the row is written, so the session is
            # still sound and the rest of the file can be checked.
            report.issues.append(ImportIssue(row.number, code, None, error.message))
            return
        report.records.append(vendor)

    def _values(
        self, reader: RowReader, code: str, current: Vendor | None
    ) -> dict[str, object]:
        """Turn one row's cells into write-schema values.

        On a create a blank cell takes the schema default. On an update a blank
        cell -- or a column the file does not have -- is left out, so it leaves
        the stored value alone.
        """
        values: dict[str, object] = {"code": code}
        name = reader.text("Name")
        if name:
            values["name"] = name
        elif current is None:
            reader.fail("Name", "is required.")
        else:
            values["name"] = current.name
        status = reader.text("Status").upper()
        if status:
            values["status"] = status
        for heading, target in _TEXT_FIELDS.items():
            if reader.text(heading):
                values[target] = reader.text(heading)
        if reader.text("GSTIN"):
            values["gst_registration"] = True
        email = reader.email("Email")
        if email:
            values["email"] = email
        for heading, target in (("Phone", "phone"), ("Mobile", "mobile")):
            phone = reader.phone(heading)
            if phone:
                values[target] = phone
        for heading, target, pool in (
            ("Category", "category_id", self._categories),
            ("Type", "type_id", self._types),
        ):
            text = reader.text(heading)
            if not text:
                continue
            found = find_master(pool, text)
            if found is None:
                reader.fail(heading, f"'{text}' is not one of the firm's.")
            else:
                values[target] = found.id
        address = self._address(reader, current)
        if address is not None:
            values["addresses"] = address
        contacts = self._contacts(reader, current)
        if contacts is not None:
            values["contacts"] = contacts
        banking = self._banking(reader, current)
        if banking is not None:
            values["banking"] = banking
        return values

    def _address(
        self, reader: RowReader, current: Vendor | None
    ) -> list[dict[str, object]] | None:
        """Build the address list, or None when the row names no address.

        On an update the supplier's other addresses are sent back unchanged,
        because the list is replaced whole and one left out is deleted.
        """
        if not any(reader.text(heading) for heading in _ADDRESS_HEADINGS):
            return None
        given: dict[str, object] = {}
        for heading, field in (
            ("Address1", "address_line1"),
            ("Address2", "address_line2"),
        ):
            if reader.text(heading):
                given[field] = reader.text(heading)
        if any(reader.text(heading) for heading in ("City", "State", "PIN", "Country")):
            # Typed places replace the ones stored, so every key is reset and
            # only what the row names is set.
            given.update(dict.fromkeys(_PLACE_KEYS))
            given.update(self._places.resolve(reader))
        stored = [item for item in (current.addresses if current else [])]
        stored = [item for item in stored if not item.is_deleted]
        target = next(
            (item for item in stored if item.is_primary),
            stored[0] if stored else None,
        )
        kept = [
            VendorAddressInput.model_validate(item).model_dump(mode="python")
            for item in stored
        ]
        if target is None:
            if "address_line1" not in given:
                reader.fail("Address1", "is needed for an address.")
            return [
                *kept,
                {"address_type": AddressType.BILLING, "is_primary": True, **given},
            ]
        for item in kept:
            if item["id"] == target.id:
                item.update(given)
        return kept

    def _contacts(
        self, reader: RowReader, current: Vendor | None
    ) -> list[dict[str, object]] | None:
        """Build the contact list, or None when the row names no contact."""
        headings = (
            "ContactName",
            "ContactDesignation",
            "ContactMobile",
            "ContactEmail",
        )
        if not any(reader.text(heading) for heading in headings):
            return None
        given: dict[str, object] = {}
        if reader.text("ContactName"):
            given["name"] = reader.text("ContactName")
        if reader.text("ContactDesignation"):
            given["designation"] = reader.text("ContactDesignation")
        mobile = reader.phone("ContactMobile")
        if mobile:
            given["mobile"] = mobile
        email = reader.email("ContactEmail")
        if email:
            given["email"] = email
        stored = [item for item in (current.contacts if current else [])]
        stored = [item for item in stored if not item.is_deleted]
        target = next(
            (item for item in stored if item.is_primary),
            stored[0] if stored else None,
        )
        kept = [
            VendorContactInput.model_validate(item).model_dump(mode="python")
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

    def _banking(
        self, reader: RowReader, current: Vendor | None
    ) -> list[dict[str, object]] | None:
        """Build the bank account list, or None when the row names none."""
        given = {
            field: (
                reader.text(heading).replace(" ", "")
                if heading in {"AccountNumber", "IFSC"}
                else reader.text(heading)
            )
            for heading, field in _BANK_FIELDS.items()
            if reader.text(heading)
        }
        if not given:
            return None
        if "ifsc" in given:
            given["ifsc"] = str(given["ifsc"]).upper()
        stored = [item for item in (current.bank_accounts if current else [])]
        stored = [item for item in stored if not item.is_deleted]
        target = next(
            (item for item in stored if item.is_primary),
            stored[0] if stored else None,
        )
        kept = [
            VendorBankInput.model_validate(item).model_dump(mode="python")
            for item in stored
        ]
        if target is None:
            for heading, field in (
                ("BankName", "bank_name"),
                ("AccountName", "account_name"),
                ("AccountNumber", "account_number"),
            ):
                if field not in given:
                    reader.fail(heading, "is needed for a bank account.")
            return [*kept, {"is_primary": True, **given}]
        for item in kept:
            if item["id"] == target.id:
                item.update(given)
        return kept


def firm_masters(
    session: Session, firm_id: UUID
) -> tuple[list[VendorCategory], list[VendorType]]:
    """Return the firm's live supplier categories and types."""
    categories = session.scalars(
        select(VendorCategory)
        .where(VendorCategory.firm_id == firm_id, VendorCategory.is_deleted.is_(False))
        .order_by(VendorCategory.code)
    ).all()
    types = session.scalars(
        select(VendorType)
        .where(VendorType.firm_id == firm_id, VendorType.is_deleted.is_(False))
        .order_by(VendorType.code)
    ).all()
    return list(categories), list(types)


def find_master(
    pool: Sequence[VendorCategory | VendorType], value: str
) -> VendorCategory | VendorType | None:
    """Find a category or type by code, then by name, ignoring case."""
    wanted = value.strip().lower()
    for item in pool:
        if item.code.lower() == wanted:
            return item
    for item in pool:
        if item.name.strip().lower() == wanted:
            return item
    return None


def template_workbook(session: Session, firm_id: UUID) -> bytes:
    """Build the XLSX template: the sheet to fill, the notes, and the lists."""
    categories, types = firm_masters(session, firm_id)
    return file_import.template_workbook(
        sheet_title="Suppliers",
        columns=COLUMNS,
        notes=[
            "One row is one supplier, with one address, one contact and one "
            "bank account; add more on the supplier's screen.",
            "City, State and PIN are looked up in the geography masters; a "
            "place they do not hold is reported, not guessed.",
            "What a supplier was owed at cutover is imported separately, as "
            "supplier opening bills.",
        ],
        lists_header=[
            "Category code",
            "Category name",
            "",
            "Type code",
            "Type name",
            "",
            "Status",
        ],
        lists=[
            [item.code for item in categories],
            [item.name for item in categories],
            [],
            [item.code for item in types],
            [item.name for item in types],
            [],
            [item.value for item in VendorStatus],
        ],
    )


def template_csv() -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(COLUMNS)
