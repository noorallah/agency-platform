"""A bill series per company: settings, resolver and counters (backlog 157).

`docs/design/BILL_SERIES_BY_COMPANY_DESIGN.md` is the reference.

* **Which series.** A firm on ``ONE_SERIES`` numbers every sales bill from
  GENERAL. On ``BY_COMPANY`` a bill whose goods lines all give the same
  company prefix takes it; a bill mixing companies, or holding a goods line
  with no company or no prefix, takes GENERAL and is never refused. Service
  lines (freight, repair) are not goods and are not counted. The levels are a
  table, :data:`SERIES_DRIVERS`: brand, goods type and product are an entry
  each, not a rewrite.
* **Which number.** The counter is keyed on firm, prefix and financial year
  (``bill_series_counters``), read ``with_for_update``. Two bills racing for
  one series queue on its row; two companies sharing a prefix share it. A
  layout that prints no year keys on the prefix alone, under
  :data:`NO_YEAR`, so its counter never restarts (design section 15).
* **Which length.** A prefix is judged at save against the firm's sales-bill
  layout, so the longest number it can print fits CGST rule 46(b).
* **Past the last number.** A series never prints more digits than its
  padding: the issue after the last is refused with :data:`LIMIT_MESSAGE`,
  and Settings warns from 95%. A new prefix is the way on -- it starts its
  own counter at 1, and the old one is kept, so going back to it carries on
  where it stopped (design section 15, decisions 4 and 5).

Only ``SALES_INVOICE`` is numbered this way; returns, notes and proformas
keep their own series (design section 9).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.audit.services import record_change, row_state
from app.core.exceptions import ValidationError
from app.document_framework.models import (
    BillSeriesCounter,
    BillSeriesSettings,
    DocumentNumberingRule,
    DocumentTypeDefinition,
)
from app.document_framework.models.bill_series import (
    BY_COMPANY,
    GENERAL_SERIES,
    ONE_SERIES,
)
from app.document_framework.models.document_framework import (
    YEAR_FORMAT_FULL,
    YEAR_FORMAT_NONE,
    YEAR_FORMAT_SHORT,
    YEAR_FORMAT_TWO_DIGIT,
    flags_for_year_format,
    year_format_of,
)
from app.document_framework.services.gst_numbering import (
    GST_NUMBER_LIMIT,
    gst_number_problem,
)

if TYPE_CHECKING:
    from datetime import date

#: The one document type numbered from the bill series.
BILL_SERIES_DOCUMENT_TYPE = "SALES_INVOICE"

#: The widest prefix the column holds; the 16-character check decides.
PREFIX_COLUMN_LENGTH = 10

#: The ``financial_year`` a series that prints no year counts under: one
#: counter for the life of the prefix, since a yearly restart would print
#: ``ASIAN/00000001`` again every April (design section 15).
NO_YEAR = ""

#: The refusal once a series has issued the last number its padding holds
#: (design section 15, decision 5), in the owner's words.
LIMIT_MESSAGE = (
    "This series has used its last number; give the company a new prefix to "
    "start a new series."
)

#: The share of a series' numbers, in per cent, from which Settings warns.
WARN_AT_PERCENT = 95

#: How many characters each year format prints.
_YEAR_LENGTH = {
    YEAR_FORMAT_NONE: 0,
    YEAR_FORMAT_TWO_DIGIT: 2,
    YEAR_FORMAT_SHORT: 5,
    YEAR_FORMAT_FULL: 9,
}

_PREFIX = re.compile(r"^[A-Z0-9]+$")

#: Product id to the prefix that product's bills would take under one level.
SeriesDriver = Callable[[Session, UUID, Sequence[UUID]], dict[UUID, str | None]]


def _by_company(
    session: Session, firm_id: UUID, product_ids: Sequence[UUID]
) -> dict[UUID, str | None]:
    """Return each product's company prefix: brand, then principal, then prefix."""
    # Imported here: products is a domain this framework otherwise does not
    # depend on.
    from app.products.models import Product
    from app.products.models.brand import Brand, Principal

    rows = session.execute(
        select(Product.id, Principal.bill_series_prefix)
        .select_from(Product)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .outerjoin(
            Principal,
            (Principal.id == Brand.principal_id) & Principal.is_deleted.is_(False),
        )
        .where(Product.id.in_(set(product_ids)), Product.firm_id == firm_id)
    ).all()
    return {product_id: prefix or None for product_id, prefix in rows}


#: Each level a firm may number its bills by, beyond ``ONE_SERIES``. A later
#: level (``BY_BRAND``, ``BY_GOODS_TYPE``, ``BY_PRODUCT``) is one entry here
#: and a prefix column on that level's master.
SERIES_DRIVERS: dict[str, SeriesDriver] = {BY_COMPANY: _by_company}


def series_drivers() -> list[str]:
    """Return every value ``series_driver`` may take, ``ONE_SERIES`` first."""
    return [ONE_SERIES, *SERIES_DRIVERS]


def normalise_prefix(value: str | None) -> str | None:
    """Return a prefix stored upper case, or ``None`` for blank.

    Raises:
        ValueError: If it holds anything but letters and digits, or is too
            long for the column.

    """
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    if not _PREFIX.match(cleaned):
        raise ValueError(
            "A bill series prefix holds letters and digits only, so it never "
            "carries a character a GST number may not."
        )
    if len(cleaned) > PREFIX_COLUMN_LENGTH:
        raise ValueError(
            f"A bill series prefix has at most {PREFIX_COLUMN_LENGTH} characters."
        )
    return cleaned


def series_key(rule: DocumentNumberingRule, series_prefix: str | None) -> str:
    """Return the counter a bill of ``series_prefix`` counts under.

    No prefix is GENERAL. So is a company prefix that prints exactly what the
    firm's own series prints -- the rule's prefix, or the word GENERAL -- since
    the two would otherwise issue the same numbers from two counters.
    """
    if not series_prefix:
        return GENERAL_SERIES
    key = series_prefix.strip().upper()
    if key in {GENERAL_SERIES, (rule.prefix or "").strip().upper()}:
        return GENERAL_SERIES
    return key


def counter_year(rule: DocumentNumberingRule, label: str) -> str:
    """Return the ``financial_year`` a bill of ``rule`` counts under.

    The full label when the number prints a year in any form, so the series
    restarts each year as it always has; :data:`NO_YEAR` when it prints none.
    """
    if rule.format_pattern:
        prints = "{financial_year" in rule.format_pattern
    else:
        prints = year_format_of(rule) != YEAR_FORMAT_NONE
    return label if prints else NO_YEAR


def series_capacity(rule: DocumentNumberingRule) -> int:
    """Return the last number ``rule``'s padding holds: 999999 for six digits."""
    return int(10**rule.sequence_padding - 1)


def is_near_limit(used: int, capacity: int) -> bool:
    """Say whether ``used`` of ``capacity`` numbers is 95% or more of them."""
    return used * 100 >= capacity * WARN_AT_PERCENT


def prefix_has_issued(session: Session, firm_id: UUID, prefix: str) -> bool:
    """Say whether any sales bill was numbered under ``prefix``, in any year."""
    return (
        session.scalar(
            select(BillSeriesCounter.id)
            .where(
                BillSeriesCounter.firm_id == firm_id,
                BillSeriesCounter.prefix == prefix,
                BillSeriesCounter.next_sequence > 1,
            )
            .limit(1)
        )
        is not None
    )


@dataclass(frozen=True, slots=True)
class SeriesChoice:
    """Which series a bill takes, and why."""

    #: The company prefix, or ``None`` for GENERAL.
    prefix: str | None
    #: ``ONE_SERIES``, ``ONE_COMPANY``, ``MIXED`` or ``NO_GOODS``.
    reason: str


def company_prefixes_in_use(session: Session, firm_id: UUID) -> list[str]:
    """Return the distinct prefixes the firm's live companies carry."""
    from app.products.models.brand import Principal

    return sorted(
        {
            prefix
            for prefix in session.scalars(
                select(Principal.bill_series_prefix).where(
                    Principal.firm_id == firm_id,
                    Principal.is_deleted.is_(False),
                    Principal.bill_series_prefix.is_not(None),
                )
            ).all()
            if prefix
        }
    )


def company_names_by_prefix(
    session: Session, firm_id: UUID, prefixes: Iterable[str | None]
) -> dict[str, str]:
    """Return the company name behind each prefix, in one read.

    Companies sharing a prefix share its series, so their names are joined.
    GENERAL and blank ask nothing.
    """
    from app.products.models.brand import Principal

    wanted = {p for p in prefixes if p and p != GENERAL_SERIES}
    if not wanted:
        return {}
    names: dict[str, list[str]] = {}
    for prefix, name in session.execute(
        select(Principal.bill_series_prefix, Principal.name).where(
            Principal.firm_id == firm_id,
            Principal.is_deleted.is_(False),
            Principal.bill_series_prefix.in_(wanted),
        )
    ).all():
        names.setdefault(prefix, []).append(name)
    return {prefix: ", ".join(sorted(group)) for prefix, group in names.items()}


def sales_bill_rule(session: Session, firm_id: UUID) -> DocumentNumberingRule | None:
    """Return the series the firm's sales bills are numbered from, if any.

    The ordering `_ensure_document_setup` uses: active first, then the
    default, then the oldest -- every key non-null.
    """
    return session.scalar(
        select(DocumentNumberingRule)
        .join(
            DocumentTypeDefinition,
            DocumentTypeDefinition.id == DocumentNumberingRule.document_type_id,
        )
        .where(
            DocumentNumberingRule.firm_id == firm_id,
            DocumentNumberingRule.is_deleted.is_(False),
            DocumentTypeDefinition.code == BILL_SERIES_DOCUMENT_TYPE,
            DocumentTypeDefinition.is_deleted.is_(False),
        )
        .order_by(
            DocumentNumberingRule.is_active.desc(),
            DocumentNumberingRule.is_default.desc(),
            DocumentNumberingRule.created_at.asc(),
            DocumentNumberingRule.id.asc(),
        )
        .limit(1)
    )


def sales_bill_layout(session: Session, firm_id: UUID) -> DocumentNumberingRule:
    """Return the firm's sales-bill series, or the one its first bill makes.

    A firm that has never raised a bill has no series yet; the layout its
    first bill will create is judged instead, so a prefix saved early is
    held to the same limit. The row returned then is transient and never
    added to the session.
    """
    rule = sales_bill_rule(session, firm_id)
    if rule is not None:
        return rule
    # Imported here: the sales invoice module depends on this framework.
    from app.sales_invoice.services.sales_invoice_service import SalesInvoiceService

    spec = SalesInvoiceService.DOCUMENT
    # As `_ensure_document_setup` will build it: the spec's year format, else
    # the short year every GST document defaults to.
    year_format = spec.year_format or YEAR_FORMAT_SHORT
    include, short = flags_for_year_format(year_format)
    return DocumentNumberingRule(
        firm_id=firm_id,
        code=spec.numbering_code,
        name=spec.numbering_name,
        prefix=spec.prefix,
        suffix=None,
        separator=spec.separator,
        format_pattern=None,
        include_financial_year=include,
        short_financial_year=short,
        year_format=year_format,
        include_branch_code=False,
        include_company_code=False,
        auto_reset=include,
        manual_allowed=False,
        sequence_padding=spec.sequence_padding,
        next_sequence=1,
        is_default=True,
        is_active=True,
    )


def _longest(session: Session, rule: DocumentNumberingRule, prefix: str | None) -> str:
    """Return the longest number ``rule`` prints under ``prefix``."""
    from app.document_framework.services.document_framework_service import (
        DocumentFrameworkService,
    )

    return DocumentFrameworkService(session).longest_number(rule, prefix=prefix)


def assert_prefix_fits(session: Session, firm_id: UUID, prefix: str) -> None:
    """Refuse a company prefix whose bills could pass 16 characters.

    Built as the longest number the series could print -- the prefix, the
    year as the rule prints it, the rule's padding filled with nines -- and
    judged by `gst_number_problem` (design section 8).

    Raises:
        ValidationError: Naming the number and the limit.

    """
    rule = sales_bill_layout(session, firm_id)
    problem = gst_number_problem(_longest(session, rule, prefix))
    if problem is not None:
        fits = longest_prefix(session, firm_id, rule=rule)
        raise ValidationError(
            f"The bill series prefix {prefix} is too long for the firm's sales "
            f"bill numbers: {problem}. With the present layout a prefix of up "
            f"to {fits} characters fits; shorten the prefix, or use fewer "
            "digits or the short year on the sales bill series."
        )


def longest_prefix(
    session: Session,
    firm_id: UUID,
    *,
    rule: DocumentNumberingRule | None = None,
) -> int:
    """Return how many characters a company prefix may have, from the layout."""
    layout = rule if rule is not None else sales_bill_layout(session, firm_id)
    fits = 0
    for length in range(1, PREFIX_COLUMN_LENGTH + 1):
        if gst_number_problem(_longest(session, layout, "W" * length)) is not None:
            break
        fits = length
    return fits


def fit_text(
    session: Session, rule: DocumentNumberingRule, prefix: str | None = None
) -> str:
    """Say how the longest number of a series fills the 16 characters.

    ``prefix 5 + separators 2 + year 2 + digits 7 = 16 of 16 characters
    (ASIAN/26/9999999)``. A rule printed from a pattern is given as a total,
    since its literals are not parts this can name.
    """
    number = _longest(session, rule, prefix)
    total = f"{len(number)} of {GST_NUMBER_LIMIT} characters ({number})"
    if rule.format_pattern:
        return total
    shown = prefix if prefix is not None else (rule.prefix or "")
    digits = max(rule.sequence_padding, len(str(rule.next_sequence or 1)))
    year = _YEAR_LENGTH.get(year_format_of(rule), 0)
    rest = len(number) - len(shown) - year - digits
    codes = rule.include_company_code or rule.include_branch_code or rule.suffix
    parts = [f"prefix {len(shown)}"]
    if rest:
        parts.append(f"{'separators and codes' if codes else 'separators'} {rest}")
    if year:
        parts.append(f"year {year}")
    parts.append(f"digits {digits}")
    return f"{' + '.join(parts)} = {total}"


class BillSeriesCounters:
    """Issue and read the next number of one bill series in one year."""

    def __init__(self, session: Session) -> None:
        """Bind to the bill's own session; nothing here commits."""
        self._session = session

    def _row(
        self, firm_id: UUID, prefix: str, year: str, *, lock: bool
    ) -> BillSeriesCounter | None:
        """Return the counter row, retired or not, locked when asked."""
        statement = select(BillSeriesCounter).where(
            BillSeriesCounter.firm_id == firm_id,
            BillSeriesCounter.prefix == prefix,
            BillSeriesCounter.financial_year == year,
        )
        if lock:
            # populate_existing: a row already in the identity map would
            # otherwise keep the version read before the lock was granted,
            # and the waiter's UPDATE would fail as stale (D-CONC-1).
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        return self._session.scalar(statement)

    def _highest(self, firm_id: UUID, prefix: str) -> int:
        """Return the highest ``next_sequence`` the prefix holds in any year.

        A series that stops printing its year carries on past every number
        it reached while it did, rather than starting again at 1.
        """
        highest = self._session.scalar(
            select(func.max(BillSeriesCounter.next_sequence)).where(
                BillSeriesCounter.firm_id == firm_id,
                BillSeriesCounter.prefix == prefix,
            )
        )
        return int(highest or 1)

    def issue(
        self,
        firm_id: UUID,
        prefix: str,
        year: str,
        *,
        floor: int,
        actor_id: UUID | None,
        ceiling: int | None = None,
    ) -> int:
        """Return the next number of the series and move its counter past it.

        The row is read ``with_for_update``, inside the bill's transaction, so
        a second bill for the same series and year waits and reads the number
        after this one. A row not there yet is inserted under a savepoint: a
        second inserter fails on the unique key and reads the winner's row
        instead. A retired row is revived, never duplicated.

        Args:
            firm_id: The firm.
            prefix: The series, ``GENERAL`` or a company prefix.
            year: The full financial-year label, ``2026-2027``, or
                :data:`NO_YEAR` for a series that prints no year.
            floor: The lowest number this issue may take -- GENERAL passes
                the rule's own counter so it never goes back behind it.
            actor_id: The user raising the bill.
            ceiling: The last number the series may issue -- its padding
                filled with nines; ``None`` sets no limit.

        Returns:
            The number issued.

        Raises:
            ValidationError: :data:`LIMIT_MESSAGE`, if the next number is past
                ``ceiling``. The counter is left where it was.

        """
        row = self._row(firm_id, prefix, year, lock=True)
        if row is None:
            if year == NO_YEAR:
                floor = max(floor, self._highest(firm_id, prefix))
            fresh = BillSeriesCounter(
                firm_id=firm_id,
                prefix=prefix,
                financial_year=year,
                next_sequence=max(floor, 1),
                created_by=actor_id,
                updated_by=actor_id,
            )
            # Opened before the row is added, so the INSERT is inside it.
            savepoint = self._session.begin_nested()
            self._session.add(fresh)
            try:
                self._session.flush()
            except IntegrityError:
                savepoint.rollback()
                row = self._row(firm_id, prefix, year, lock=True)
                if row is None:
                    raise
            else:
                savepoint.commit()
                row = fresh
        if row.is_deleted:
            row.is_deleted = False
            row.deleted_at = None
        sequence = max(row.next_sequence, floor, 1)
        if ceiling is not None and sequence > ceiling:
            raise ValidationError(LIMIT_MESSAGE)
        row.next_sequence = sequence + 1
        if actor_id is not None:
            row.updated_by = actor_id
        self._session.flush()
        return sequence

    def peek(self, firm_id: UUID, prefix: str, year: str) -> int:
        """Return the number the series would issue next, writing nothing."""
        row = self._row(firm_id, prefix, year, lock=False)
        if row is not None:
            return row.next_sequence
        return self._highest(firm_id, prefix) if year == NO_YEAR else 1


class BillSeriesSettingsWrite(BaseModel):
    """Choose which series the firm's sales bills take."""

    model_config = ConfigDict(extra="forbid")

    series_driver: str = Field(min_length=1, max_length=30)


class BillSeriesUsage(BaseModel):
    """How much of one series is used, and how its numbers fit 16 characters."""

    model_config = ConfigDict(extra="forbid")

    #: ``GENERAL`` or the company prefix.
    series_prefix: str
    #: The companies behind the prefix, joined; ``None`` for GENERAL or a
    #: prefix no live company carries any more.
    company_name: str | None
    #: The last number the series issued, 0 for none yet.
    last_issued: int
    #: The last number its padding holds: 9999999 for seven digits.
    capacity: int
    #: 95% or more of its numbers are used.
    near_limit: bool
    #: Its last number is issued; the next bill of the series is refused.
    at_limit: bool
    #: What Settings shows when ``near_limit``: the limit message once
    #: ``at_limit``, else how much is left. ``None`` while there is room.
    warning: str | None
    #: ``prefix 5 + separators 2 + year 2 + digits 7 = 16 of 16 characters
    #: (ASIAN/26/9999999)``.
    fit: str


class BillSeriesSettingsResponse(BaseModel):
    """The firm's bill series setting, and what a company prefix may be."""

    model_config = ConfigDict(extra="forbid")

    series_driver: str
    #: Every value ``series_driver`` may take.
    drivers: list[str]
    #: How many characters a company prefix may have under the present
    #: sales-bill layout -- worked out, never written into a sentence.
    longest_prefix: int
    is_configured: bool
    #: Every series of the present year, GENERAL first: how much of each is
    #: used and how its numbers fit (design section 15 (d)).
    series: list[BillSeriesUsage] = Field(default_factory=list)


class BillSeriesPreview(BaseModel):
    """Which series a bill of these lines takes, and the number it would get."""

    model_config = ConfigDict(extra="forbid")

    series_driver: str
    #: ``GENERAL`` or the company prefix.
    series_prefix: str
    #: ``ONE_SERIES``, ``ONE_COMPANY``, ``MIXED`` or ``NO_GOODS``.
    reason: str
    number: str


class BillSeriesService:
    """Keep the firm's setting and resolve a bill's series from its lines."""

    def __init__(self, session: Session) -> None:
        """Bind to the request's session."""
        self._session = session

    def _settings_row(self, firm_id: UUID) -> BillSeriesSettings | None:
        return self._session.scalar(
            select(BillSeriesSettings).where(
                BillSeriesSettings.firm_id == firm_id,
                BillSeriesSettings.is_deleted.is_(False),
            )
        )

    def driver_for(self, firm_id: UUID) -> str:
        """Return the firm's ``series_driver``; a firm with no row is ONE_SERIES."""
        row = self._settings_row(firm_id)
        return row.series_driver if row is not None else ONE_SERIES

    def settings(self, firm_id: UUID) -> BillSeriesSettingsResponse:
        """Return the firm's setting with the prefix length its layout allows."""
        row = self._settings_row(firm_id)
        return BillSeriesSettingsResponse(
            series_driver=row.series_driver if row is not None else ONE_SERIES,
            drivers=series_drivers(),
            longest_prefix=longest_prefix(self._session, firm_id),
            is_configured=row is not None,
            series=self.usage(firm_id),
        )

    def usage(self, firm_id: UUID) -> list[BillSeriesUsage]:
        """Return each series of the present year: GENERAL, then by prefix.

        A series is listed when a live company carries its prefix or when it
        has a counter this year -- so a prefix a company has moved off is
        still shown, since going back to it carries on where it stopped.
        """
        from app.common.firm_metadata import firm_today
        from app.document_framework.services.document_framework_service import (
            DocumentFrameworkService,
        )

        numbers = DocumentFrameworkService(self._session)
        rule = sales_bill_layout(self._session, firm_id)
        today = firm_today(self._session, firm_id)
        year = counter_year(rule, numbers._year_label(firm_id, today, None))
        counted = self._session.scalars(
            select(BillSeriesCounter.prefix).where(
                BillSeriesCounter.firm_id == firm_id,
                BillSeriesCounter.financial_year == year,
                BillSeriesCounter.is_deleted.is_(False),
            )
        ).all()
        keys = {GENERAL_SERIES}
        keys.update(series_key(rule, prefix) for prefix in counted)
        keys.update(
            series_key(rule, prefix)
            for prefix in company_prefixes_in_use(self._session, firm_id)
        )
        ordered = [GENERAL_SERIES, *sorted(keys - {GENERAL_SERIES})]
        names = company_names_by_prefix(self._session, firm_id, ordered)
        capacity = series_capacity(rule)
        answer: list[BillSeriesUsage] = []
        for key in ordered:
            prefix = None if key == GENERAL_SERIES else key
            used = (
                numbers.next_bill_sequence(
                    rule, series_prefix=prefix, document_date=today
                )
                - 1
            )
            near = is_near_limit(used, capacity)
            at = used >= capacity
            warning: str | None = None
            if at:
                warning = LIMIT_MESSAGE
            elif near:
                warning = (
                    f"The series {key} has used {used:,} of its {capacity:,} "
                    f"numbers, {capacity - used:,} left; give the company a "
                    "new prefix before it runs out."
                )
            answer.append(
                BillSeriesUsage(
                    series_prefix=key,
                    company_name=names.get(key),
                    last_issued=used,
                    capacity=capacity,
                    near_limit=near,
                    at_limit=at,
                    warning=warning,
                    fit=fit_text(self._session, rule, prefix),
                )
            )
        return answer

    def save_settings(
        self, data: BillSeriesSettingsWrite, *, firm_id: UUID, actor_id: UUID
    ) -> BillSeriesSettingsResponse:
        """Replace the firm's setting, flushed and audited; the caller commits.

        Switching at any time is safe: counters are per prefix and year, so
        GENERAL carries on wherever it was and nothing is reset.

        Raises:
            ValidationError: If the value is not one this build numbers by.

        """
        driver = data.series_driver.strip().upper()
        allowed = series_drivers()
        if driver not in allowed:
            raise ValidationError(
                f"{data.series_driver} is not a bill series setting. Choose one "
                f"of {', '.join(allowed)}."
            )
        row = self._settings_row(firm_id)
        before = None if row is None else row_state(row)
        if row is None:
            row = BillSeriesSettings(
                firm_id=firm_id,
                series_driver=driver,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(row)
        else:
            row.series_driver = driver
            row.updated_by = actor_id
        self._session.flush()
        record_change(
            self._session,
            action="bill_series_settings.saved",
            entity_type="bill_series_settings",
            row=row,
            actor_id=actor_id,
            before=before,
            firm_id=firm_id,
        )
        return self.settings(firm_id)

    def resolve(
        self,
        firm_id: UUID,
        product_ids: Iterable[UUID],
        *,
        driver: str | None = None,
    ) -> SeriesChoice:
        """Return the series a bill of these products takes (design section 6).

        Args:
            firm_id: The firm.
            product_ids: One per bill line, as saved.
            driver: The level to resolve by; the firm's own when omitted.

        Returns:
            The company prefix and why, or ``None`` for GENERAL.

        """
        level = driver if driver is not None else self.driver_for(firm_id)
        lookup = SERIES_DRIVERS.get(level)
        if lookup is None:
            return SeriesChoice(None, ONE_SERIES)
        # Imported here: products is a domain this framework otherwise does
        # not depend on.
        from app.products.services.stockless import stockless_products

        ids = [product_id for product_id in product_ids if product_id is not None]
        services = stockless_products(self._session, ids)
        goods = [product_id for product_id in ids if product_id not in services]
        if not goods:
            return SeriesChoice(None, "NO_GOODS")
        prefixes = lookup(self._session, firm_id, goods)
        found = {prefixes.get(product_id) for product_id in goods}
        if len(found) == 1 and None not in found:
            prefix = found.pop()
            assert prefix is not None
            return SeriesChoice(prefix, "ONE_COMPANY")
        return SeriesChoice(None, "MIXED")

    def preview(
        self, firm_id: UUID, product_ids: Iterable[UUID], *, on: date
    ) -> BillSeriesPreview:
        """Return the series and the number a bill of these products would take.

        Writes nothing: a firm that has never billed is shown the layout its
        first bill will create.
        """
        from app.document_framework.services.document_framework_service import (
            DocumentFrameworkService,
        )

        choice = self.resolve(firm_id, product_ids)
        rule = sales_bill_layout(self._session, firm_id)
        number = DocumentFrameworkService(self._session).preview_bill_number(
            rule, series_prefix=choice.prefix, document_date=on
        )
        return BillSeriesPreview(
            series_driver=self.driver_for(firm_id),
            series_prefix=series_key(rule, choice.prefix),
            reason=choice.reason,
            number=number,
        )


__all__ = [
    "BILL_SERIES_DOCUMENT_TYPE",
    "BY_COMPANY",
    "GENERAL_SERIES",
    "NO_YEAR",
    "ONE_SERIES",
    "SERIES_DRIVERS",
    "BillSeriesCounters",
    "BillSeriesPreview",
    "BillSeriesService",
    "BillSeriesSettingsResponse",
    "BillSeriesSettingsWrite",
    "BillSeriesUsage",
    "LIMIT_MESSAGE",
    "SeriesChoice",
    "assert_prefix_fits",
    "company_names_by_prefix",
    "company_prefixes_in_use",
    "counter_year",
    "fit_text",
    "is_near_limit",
    "longest_prefix",
    "normalise_prefix",
    "prefix_has_issued",
    "sales_bill_layout",
    "sales_bill_rule",
    "series_capacity",
    "series_key",
]
