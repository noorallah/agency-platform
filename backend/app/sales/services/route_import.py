"""Bring a firm's routes (beats) in from a spreadsheet, with a template to fill in.

Swathi gap G3. The rules every master import keeps -- check every row, write
all or nothing, match headings loosely, update on request -- live in
``app.common.file_import``. What is particular to routes:

* **A route is a territory node with a round.** A row makes a node one level
  below the area it names and gives it a route profile -- type, how often it
  is visited, which days -- exactly what *This is a route* on the territory
  form does. A row without a *Parent* sits at the top level.
* **The file makes routes, not areas.** The area a route is under is a choice,
  and a guessed one is wrong silently, so a *Parent* must already exist; so
  must a *Type*. A code already held by an area is refused rather than turned
  into a route.
* **Every row goes through** ``SalesTerritoryService.stage_create_territory``
  or ``stage_update_territory`` -- the same code, name and level checks and
  audit row as the form -- and the file commits once.
"""

# ruff: noqa: D102, D107

import re
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
    service_issue,
)
from app.core.exceptions import ApplicationError
from app.sales.models import (
    RouteTypeMaster,
    SalesHierarchyConfig,
    SalesHierarchyLevel,
    SalesTerritoryNode,
    TerritoryRouteProfile,
    TerritoryWorkingDay,
)
from app.sales.schemas import TerritoryCreate, TerritoryUpdate
from app.sales.schemas.territory import TerritoryStatus, VisitFrequency
from app.sales.services.territory_service import SalesTerritoryService

#: The template, in the order it is laid out.
COLUMNS: tuple[Column, ...] = (
    Column(
        "Code",
        ("routecode", "beatcode"),
        True,
        "The route's code: capitals, digits, - and _; unique among the firm's "
        "territories.",
        "BEAT-01",
    ),
    Column(
        "Name",
        ("routename", "beatname", "route", "beat"),
        False,
        "The route's name. Needed for a new route.",
        "Market Road",
    ),
    Column(
        "Parent",
        ("parentcode", "area", "areacode", "territory", "territorycode", "under"),
        False,
        "The area the route is under, by code or name (see the Lists sheet). "
        "Blank puts a new route at the top level.",
        "SOUTH",
    ),
    Column(
        "Type",
        ("routetype", "beattype"),
        False,
        "The route type, by code or name (see the Lists sheet). May be blank.",
        "URBAN",
    ),
    Column(
        "Frequency",
        ("visitfrequency", "visits"),
        False,
        "Daily, Weekly, Fortnightly, Monthly, Quarterly or On demand. Blank "
        "means On demand for a new route.",
        "Weekly",
    ),
    Column(
        "Days",
        ("workingdays", "visitdays", "weekdays", "day"),
        False,
        "The days it is worked, as Mon, Tue ... Sun or 1-7 (1 is Monday), "
        "separated by commas. Blank means every day for a new route.",
        "Mon, Thu",
    ),
    Column(
        "Status",
        ("state",),
        False,
        "Active, Inactive, Draft or Archived. Blank means Active for a new route.",
        "Active",
    ),
)

#: The write-schema field each heading fills, for naming a schema refusal.
_FIELD_HEADINGS: dict[str, str] = {
    "code": "Code",
    "name": "Name",
    "parent_id": "Parent",
    "hierarchy_level_id": "Parent",
    "status": "Status",
    "route_profile": "Days",
    "route_profile.route_type_id": "Type",
    "route_profile.visit_frequency": "Frequency",
    "route_profile.working_days": "Days",
}

#: Weekday names as written, to their ISO number (Monday is 1).
_WEEKDAYS: dict[str, int] = {
    name: number
    for number, full in enumerate(
        (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ),
        start=1,
    )
    for name in (full, full[:3], str(number))
}


class RouteFileImporter(FileImporter[SalesTerritoryNode]):
    """Check a route file row by row, and import it whole or not at all."""

    COLUMNS = COLUMNS
    NOUN = "route"

    def __init__(self, session: Session, service: SalesTerritoryService) -> None:
        super().__init__(session)
        self._service = service
        self._levels: list[SalesHierarchyLevel] = []
        self._nodes: list[SalesTerritoryNode] = []
        self._route_types: list[RouteTypeMaster] = []
        self._profiles: dict[UUID, TerritoryRouteProfile] = {}
        self._days: dict[UUID, list[int]] = {}

    def _prepare(self, firm_id: UUID) -> None:
        # Read directly rather than through ``get_hierarchy``, which makes the
        # default levels and commits: a check must write nothing.
        self._levels = firm_levels(self._session, firm_id)
        self._nodes = firm_areas(self._session, firm_id)
        self._route_types = firm_route_types(self._session, firm_id)
        node_ids = [node.id for node in self._nodes]
        self._profiles = {
            profile.territory_id: profile
            for profile in self._session.scalars(
                select(TerritoryRouteProfile).where(
                    TerritoryRouteProfile.territory_id.in_(node_ids),
                    TerritoryRouteProfile.is_deleted.is_(False),
                )
            ).all()
        }
        self._days = {}
        profile_ids = {profile.id: tid for tid, profile in self._profiles.items()}
        for day in self._session.scalars(
            select(TerritoryWorkingDay).where(
                TerritoryWorkingDay.route_profile_id.in_(list(profile_ids)),
                TerritoryWorkingDay.is_deleted.is_(False),
            )
        ).all():
            territory_id = profile_ids[day.route_profile_id]
            self._days.setdefault(territory_id, []).append(day.weekday)

    def _stored(self, firm_id: UUID) -> dict[str, SalesTerritoryNode]:
        return {node.code.strip().upper(): node for node in self._nodes}

    def _commit(self) -> None:
        self._session.commit()

    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: SalesTerritoryNode | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[SalesTerritoryNode],
    ) -> None:
        issues: list[ImportIssue] = []
        reader = RowReader(row, code, issues)
        if current is not None and current.id not in self._profiles:
            reader.fail(
                "Code",
                "is an area, not a route; this file changes routes only. Give "
                "the route another code.",
            )
            report.issues.extend(issues)
            return
        values = self._values(reader, code, current)
        if issues:
            report.issues.extend(issues)
            return
        try:
            if current is None:
                node = self._service.stage_create_territory(
                    TerritoryCreate.model_validate(values),
                    firm_scope=firm_id,
                    actor_id=actor_id,
                )
            else:
                node = self._service.stage_update_territory(
                    current.id,
                    TerritoryUpdate.model_validate(values),
                    firm_scope=firm_id,
                    actor_id=actor_id,
                )
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _FIELD_HEADINGS))
            return
        except ApplicationError as error:
            report.issues.append(service_issue(error, row, code, _FIELD_HEADINGS))
            return
        if current is None:
            report.to_create += 1
        else:
            report.to_update += 1
        report.records.append(node)

    def _values(
        self, reader: RowReader, code: str, current: SalesTerritoryNode | None
    ) -> dict[str, object]:
        """Turn one row's cells into write-schema values.

        On an update a blank cell, or a column the file does not have, keeps
        what the route already holds; the route profile is written whole, so
        its blank parts are filled from the stored one.
        """
        values: dict[str, object] = {}
        if current is None:
            values["code"] = code
        name = reader.text("Name").strip()
        if name:
            values["name"] = name
        elif current is None:
            reader.fail("Name", "is needed for a new route.")
        parent_text = reader.text("Parent").strip()
        parent = self._parent(reader, parent_text) if parent_text else None
        if (parent is not None) or (current is None and not parent_text):
            level = self._level_below(parent)
            if level is None:
                reader.fail(
                    "Parent",
                    (
                        "has no territory level below it; add one on the "
                        "Territories screen, or name another area."
                        if parent is not None
                        else "is needed: the firm's territory levels are not set "
                        "up. Open the Territories screen once to make them."
                    ),
                )
            else:
                values["parent_id"] = None if parent is None else parent.id
                values["hierarchy_level_id"] = level.id
        status = reader.text("Status").strip()
        if status:
            wanted = status.upper().replace(" ", "_")
            if wanted in TerritoryStatus.__members__:
                values["status"] = wanted
            else:
                reader.fail(
                    "Status",
                    f"'{status}' should be Active, Inactive, Draft or Archived.",
                )
        values["route_profile"] = self._profile(reader, current)
        return values

    def _parent(self, reader: RowReader, value: str) -> SalesTerritoryNode | None:
        """Find the named area by code, then by name, failing the row if not."""
        wanted = value.strip().lower()
        for node in self._nodes:
            if node.code.lower() == wanted:
                return node
        named = [node for node in self._nodes if node.name.strip().lower() == wanted]
        if len(named) == 1:
            return named[0]
        if named:
            reader.fail("Parent", f"'{value}' names more than one area; give its code.")
        else:
            reader.fail(
                "Parent",
                f"'{value}' is not one of the firm's territories; add the area "
                "first, or name one on the Lists sheet.",
            )
        return None

    def _level_below(
        self, parent: SalesTerritoryNode | None
    ) -> SalesHierarchyLevel | None:
        """Return the level one below the parent's, or the top level."""
        order = 1
        if parent is not None:
            parent_level = next(
                (lv for lv in self._levels if lv.id == parent.hierarchy_level_id),
                None,
            )
            if parent_level is None:
                return None
            order = parent_level.level_order + 1
        return next((lv for lv in self._levels if lv.level_order == order), None)

    def _profile(
        self, reader: RowReader, current: SalesTerritoryNode | None
    ) -> dict[str, object]:
        """Build the whole route profile, keeping the stored parts left blank."""
        stored = None if current is None else self._profiles.get(current.id)
        profile: dict[str, object] = {}
        if stored is not None:
            profile = {
                "route_type_id": stored.route_type_id,
                "visit_frequency": stored.visit_frequency,
                "effective_from": stored.effective_from,
                "effective_to": stored.effective_to,
                "city_id": stored.city_id,
                "postal_code_id": stored.postal_code_id,
                "locality_id": stored.locality_id,
                "working_days": (
                    sorted(self._days.get(current.id, []))
                    if current is not None
                    else []
                ),
            }
        route_type = reader.text("Type").strip()
        if route_type:
            found = find_route_type(self._route_types, route_type)
            if found is None:
                reader.fail(
                    "Type",
                    f"'{route_type}' is not one of the firm's route types; add "
                    "it first, or name one on the Lists sheet.",
                )
            else:
                profile["route_type_id"] = found.id
        frequency = reader.text("Frequency").strip()
        if frequency:
            wanted = re.sub(r"[\s-]+", "_", frequency.upper())
            if wanted in VisitFrequency.__members__:
                profile["visit_frequency"] = wanted
            else:
                reader.fail(
                    "Frequency",
                    f"'{frequency}' should be Daily, Weekly, Fortnightly, "
                    "Monthly, Quarterly or On demand.",
                )
        days = reader.text("Days").strip()
        if days:
            parsed = parse_days(days)
            if parsed is None:
                reader.fail(
                    "Days",
                    f"'{days}' should name days as Mon ... Sun or 1-7, "
                    "separated by commas.",
                )
            else:
                profile["working_days"] = parsed
        return profile


def parse_days(value: str) -> list[int] | None:
    """Read weekdays written as names or ISO numbers; None if one will not read."""
    days: set[int] = set()
    for token in re.split(r"[,;/\s]+", value.strip().lower()):
        if not token:
            continue
        if token not in _WEEKDAYS:
            return None
        days.add(_WEEKDAYS[token])
    return sorted(days)


def firm_levels(session: Session, firm_id: UUID) -> list[SalesHierarchyLevel]:
    """Return the firm's enabled hierarchy levels, top first."""
    return list(
        session.scalars(
            select(SalesHierarchyLevel)
            .join(
                SalesHierarchyConfig,
                SalesHierarchyConfig.id == SalesHierarchyLevel.config_id,
            )
            .where(
                SalesHierarchyConfig.firm_id == firm_id,
                SalesHierarchyConfig.is_deleted.is_(False),
                SalesHierarchyLevel.is_deleted.is_(False),
                SalesHierarchyLevel.is_enabled.is_(True),
            )
            .order_by(SalesHierarchyLevel.level_order)
        ).all()
    )


def firm_areas(session: Session, firm_id: UUID) -> list[SalesTerritoryNode]:
    """Return the firm's live territory nodes by path."""
    return list(
        session.scalars(
            select(SalesTerritoryNode)
            .where(
                SalesTerritoryNode.firm_id == firm_id,
                SalesTerritoryNode.is_deleted.is_(False),
            )
            .order_by(SalesTerritoryNode.path)
        ).all()
    )


def firm_route_types(session: Session, firm_id: UUID) -> list[RouteTypeMaster]:
    """Return the firm's live, active route types by code."""
    return list(
        session.scalars(
            select(RouteTypeMaster)
            .where(
                RouteTypeMaster.firm_id == firm_id,
                RouteTypeMaster.is_deleted.is_(False),
                RouteTypeMaster.is_active.is_(True),
            )
            .order_by(RouteTypeMaster.code)
        ).all()
    )


def find_route_type(pool: list[RouteTypeMaster], value: str) -> RouteTypeMaster | None:
    """Find a route type by code, then by name, ignoring case."""
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
    areas = firm_areas(session, firm_id)
    route_types = firm_route_types(session, firm_id)
    return file_import.template_workbook(
        sheet_title="Routes",
        columns=COLUMNS,
        notes=[
            "One row is one route (beat). Its code is its key: a row whose code "
            "is already a route updates it when you choose to update.",
            "A route sits one level below the area named in Parent. The area "
            "and the route type must already exist; the file does not make "
            "them.",
        ],
        lists_header=["Area code", "Area name", "Route type code", "Route type"],
        lists=[
            [item.code for item in areas],
            [item.name for item in areas],
            [item.code for item in route_types],
            [item.name for item in route_types],
        ],
    )


def template_csv() -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(COLUMNS)
