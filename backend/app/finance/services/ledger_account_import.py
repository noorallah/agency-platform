"""Bring a firm's chart of accounts in from a spreadsheet.

Swathi gap G6, part 1. The rules every master import keeps -- check every row,
write all or nothing, match headings loosely, update on request -- live in
``app.common.file_import``. What is particular to ledger accounts:

* **An account's code is its key.** A row whose code is already an account
  updates it when the caller asks to update, and is refused otherwise.
* **Every account sits under an account group the firm already has**, named
  in *Group* by its code or its name, whatever the case. An unknown group is
  refused rather than made up: the groups are the shape of every report, and
  a guessed one is wrong silently. The account takes its group's type, so the
  file has no type column to disagree with it.
* **Every row goes through** ``FinanceService.create_ledger_account`` or
  ``update_ledger_account`` -- the same type, code and control-account rules
  and audit writes as the form. Both already flush without committing (the
  finance router owns its commits), so they are this import's stage methods
  as they stand, and the file commits once.
* **Opening balances are not part of it**; the opening trial balance has its
  own import.
"""

# ruff: noqa: D102, D107

from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
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
    service_issue,
)
from app.core.exceptions import ApplicationError, ConflictError
from app.finance.models.finance import AccountGroup, LedgerAccount
from app.finance.schemas import LedgerAccountCreate, LedgerAccountUpdate
from app.finance.services.finance_service import FinanceService

#: The template, in the order it is laid out.
COLUMNS: tuple[Column, ...] = (
    Column(
        "Code",
        ("accountcode", "ledgercode", "acccode", "accode", "glcode"),
        True,
        "The account's code: capital letters, digits, - and _, up to 20 "
        "characters; unique among the firm's accounts.",
        "4100",
    ),
    Column(
        "Name",
        ("accountname", "ledgername", "ledger", "accname", "acname"),
        False,
        "The account's name, up to 100 characters. Needed for a new account.",
        "Sales - Local",
    ),
    Column(
        "Group",
        (
            "accountgroup",
            "groupcode",
            "groupname",
            "under",
            "acchead",
            "accounthead",
        ),
        False,
        "The account group it sits under, by code or name (see the Lists "
        "sheet). Needed for a new account; the account takes the group's type.",
        "SALES",
    ),
    Column(
        "Description",
        ("remarks", "notes", "note", "narration"),
        False,
        "Anything worth keeping about the account. May be blank.",
        "",
    ),
    Column(
        "Cost Centre",
        ("costcenter", "requirescostcentre", "requirescostcenter"),
        False,
        "Yes or No: whether every line posted to it must name a cost centre. "
        "Blank means No for a new account.",
        "No",
    ),
    Column(
        "Profit Centre",
        ("profitcenter", "requiresprofitcentre", "requiresprofitcenter"),
        False,
        "Yes or No: whether every line posted to it must name a profit centre. "
        "Blank means No for a new account.",
        "No",
    ),
    Column(
        "Active",
        ("isactive", "enabled", "inuse"),
        False,
        "Yes or No. Blank means Yes for a new account.",
        "Yes",
    ),
)

#: The write-schema field each heading fills, for naming a schema refusal.
_FIELD_HEADINGS: dict[str, str] = {
    "code": "Code",
    "name": "Name",
    "account_group_id": "Group",
    "account_type": "Group",
    "description": "Description",
    "requires_cost_center": "Cost Centre",
    "requires_profit_center": "Profit Centre",
    "is_active": "Active",
}


class LedgerAccountFileImporter(FileImporter[LedgerAccount]):
    """Check a chart-of-accounts file row by row, and import it whole or not."""

    COLUMNS = COLUMNS
    NOUN = "ledger account"

    def __init__(self, session: Session, service: FinanceService) -> None:
        super().__init__(session)
        self._service = service
        self._groups_by_code: dict[str, AccountGroup] = {}
        self._groups_by_name: dict[str, list[AccountGroup]] = {}

    def _prepare(self, firm_id: UUID) -> None:
        self._groups_by_code = {}
        self._groups_by_name = {}
        for group in self._service.list_account_groups(firm_id=firm_id):
            self._groups_by_code[group.code.strip().upper()] = group
            self._groups_by_name.setdefault(group.name.strip().casefold(), []).append(
                group
            )

    def _stored(self, firm_id: UUID) -> dict[str, LedgerAccount]:
        return {
            account.code.strip().upper(): account
            for account in self._service.list_ledger_accounts(firm_id=firm_id)
        }

    def _commit(self) -> None:
        self._session.commit()

    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: LedgerAccount | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[LedgerAccount],
    ) -> None:
        issues: list[ImportIssue] = []
        values = self._values(RowReader(row, code, issues), code, current)
        if issues:
            report.issues.extend(issues)
            return
        try:
            if current is None:
                account = self._service.create_ledger_account(
                    LedgerAccountCreate.model_validate(values),
                    firm_id=firm_id,
                    actor_id=actor_id,
                )
            else:
                values.pop("code")
                values.pop("account_type", None)
                account = self._service.update_ledger_account(
                    current.id,
                    LedgerAccountUpdate.model_validate(values),
                    firm_id=firm_id,
                    actor_id=actor_id,
                )
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _FIELD_HEADINGS))
            return
        except ApplicationError as error:
            # Every guard runs before the row is written, and the insert runs
            # in its own savepoint, so the rest of the file can be checked.
            issue = service_issue(error, row, code, _FIELD_HEADINGS)
            if issue.column is None and isinstance(error, ConflictError):
                # Kept by a deleted account: the code is still taken.
                issue.column = "Code"
            elif issue.column is None and values.get("is_active") is False:
                # A control account cannot be switched off (D-FIN-8).
                issue.column = "Active"
            report.issues.append(issue)
            return
        if current is None:
            report.to_create += 1
        else:
            report.to_update += 1
        report.records.append(account)

    def _values(
        self, reader: RowReader, code: str, current: LedgerAccount | None
    ) -> dict[str, object]:
        """Turn one row's cells into write-schema values.

        An update changes only what it is sent, so on an update a blank cell,
        or a column the file does not have, is left out and keeps what the
        account held.
        """
        values: dict[str, object] = {"code": code}
        name = reader.text("Name").strip()
        if name:
            values["name"] = name
        elif current is None:
            reader.fail("Name", "is needed for a new ledger account.")
        group = self._group(reader, current)
        if group is not None:
            values["account_group_id"] = group.id
            values["account_type"] = group.account_type
        description = reader.text("Description").strip()
        if description:
            values["description"] = description
        for heading, field in (
            ("Cost Centre", "requires_cost_center"),
            ("Profit Centre", "requires_profit_center"),
            ("Active", "is_active"),
        ):
            flag = reader.flag(heading)
            if flag is not None:
                values[field] = flag
        return values

    def _group(
        self, reader: RowReader, current: LedgerAccount | None
    ) -> AccountGroup | None:
        """Find the group a row names, by code first and then by name.

        Records the problem and returns None when the cell is blank on a new
        account, names no group, names two by the same name, or names a group
        of another type than an existing account's.
        """
        raw = reader.text("Group").strip()
        if not raw:
            if current is None:
                reader.fail("Group", "is needed for a new ledger account.")
            return None
        group = self._groups_by_code.get(raw.upper())
        if group is None:
            named = self._groups_by_name.get(raw.casefold(), [])
            if len(named) > 1:
                codes = ", ".join(sorted(item.code for item in named))
                reader.fail(
                    "Group",
                    f"'{raw}' is the name of more than one group ({codes}); "
                    "give the group's code.",
                )
                return None
            group = named[0] if named else None
        if group is None:
            reader.fail(
                "Group",
                f"'{raw}' is not one of the firm's account groups. Give a group "
                "code or name from the Lists sheet, or add the group first.",
            )
            return None
        if current is not None and group.account_type != current.account_type:
            reader.fail(
                "Group",
                f"{group.code} holds {group.account_type} accounts and "
                f"{current.code} is {current.account_type}; an account can only "
                "move to a group of its own type.",
            )
            return None
        return group


def template_workbook(session: Session, firm_id: UUID) -> bytes:
    """Build the XLSX template: the sheet to fill, the notes, and the lists."""
    service = FinanceService(session)
    groups = list(service.list_account_groups(firm_id=firm_id))
    accounts = list(service.list_ledger_accounts(firm_id=firm_id))
    return file_import.template_workbook(
        sheet_title="Ledger accounts",
        columns=COLUMNS,
        notes=[
            "One row is one ledger account. Its code is its key: a row whose "
            "code is already an account updates it when you choose to update.",
            "Every account sits under one of the firm's account groups, named "
            "by code or name, and takes that group's type. Add a missing group "
            "on the chart of accounts screen first.",
            "Opening balances are not set here; use the opening trial balance "
            "import.",
        ],
        lists_header=[
            "Group code",
            "Group name",
            "Group type",
            "Account code",
            "Account name",
        ],
        lists=[
            [group.code for group in groups],
            [group.name for group in groups],
            [group.account_type for group in groups],
            [account.code for account in accounts],
            [account.name for account in accounts],
        ],
    )


def template_csv() -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(COLUMNS)
