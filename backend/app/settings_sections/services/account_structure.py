"""The Account structure subject: control accounts and the centres beside them.

Every reader selects and nothing else, like the Tax subject's.

**Control accounts are owed.** Every automatic posting asks
``ControlAccountService.resolve`` for the account a purpose posts to, and it
raises ``ValidationError`` for a purpose the firm has not mapped -- so a
document that needs that purpose cannot be posted. The step is TODO while any
purpose is unmapped, counted by the same ``missing`` call over the same
``ALL_PURPOSES`` that the firm's readiness check uses.

Cost and profit centres are OPTIONAL, except where the firm has marked a live
ledger account as requiring one and holds no active centre: the journal engine
refuses every line on such an account that names no centre, so that is TODO.
"""

from uuid import UUID

from sqlalchemy.orm import InstrumentedAttribute, Session

from app.finance.models.finance import CostCenter, LedgerAccount, ProfitCenter
from app.finance.services.control_accounts import ControlAccountService
from app.firms.services.readiness import ALL_PURPOSES
from app.settings_sections.services.steps import (
    DONE,
    NONE_YET,
    OPTIONAL,
    TODO,
    SettingsStep,
    counted,
    live_count,
)


def _control_accounts_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Say how many posting purposes the firm has left unmapped."""
    unmapped = ControlAccountService(session).missing(firm_id, ALL_PURPOSES)
    total = len(ALL_PURPOSES)
    if not unmapped:
        return SettingsStep("control-accounts", DONE, f"All {total} mapped")
    return SettingsStep(
        "control-accounts", TODO, f"{len(unmapped)} of {total} unmapped"
    )


def _centre_step(
    session: Session,
    firm_id: UUID,
    code: str,
    model: type[CostCenter] | type[ProfitCenter],
    requires: InstrumentedAttribute[bool],
) -> SettingsStep:
    """Count the firm's active centres, owed only where an account needs one."""
    centres = live_count(session, model, firm_id, model.is_active.is_(True))
    if centres:
        return SettingsStep(code, OPTIONAL, counted(centres, "centre", "centres"))
    needing = live_count(
        session,
        LedgerAccount,
        firm_id,
        LedgerAccount.is_active.is_(True),
        requires.is_(True),
    )
    if not needing:
        return SettingsStep(code, OPTIONAL, NONE_YET)
    accounts = counted(needing, "account needs", "accounts need")
    return SettingsStep(code, TODO, f"{NONE_YET}: {accounts} one")


def account_structure_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the three steps of the Account structure subject, in set-up order."""
    return [
        _control_accounts_step(session, firm_id),
        _centre_step(
            session,
            firm_id,
            "cost-centers",
            CostCenter,
            LedgerAccount.requires_cost_center,
        ),
        _centre_step(
            session,
            firm_id,
            "profit-centers",
            ProfitCenter,
            LedgerAccount.requires_profit_center,
        ),
    ]


__all__ = ["account_structure_section"]
