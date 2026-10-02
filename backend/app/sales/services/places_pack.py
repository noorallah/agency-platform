"""Load districts, towns, PIN codes and localities from India Post (decision B6).

Backlog 41. The state master is seeded; the four rungs below it were typed by
hand, and they are the ones with volume. The pack shipped with the server
(``app/sales/data/india_post_pincodes.csv.gz``, built by
``scripts/build_places_pack.py`` from the Department of Posts' directory on
data.gov.in, Government Open Data Licence - India) fills them for the states a
firm chooses -- offline, from a file inside the installer, never from the
internet.

India Post's directory runs state, district, PIN code, post office. The masters
have a town between district and PIN code, so each PIN code's town is named
after its own delivering office -- its head office or sub-office, the one that
is not a village branch -- and every office under the PIN, branches included,
becomes a locality. That is how a PIN lookup reads in Zoho and Tally: type the
PIN, get the area, the district and the state.

**The seed skips; it never merges** (as ``20260917_0137`` does for states). A
place the store already holds by name -- typed by a firm, or loaded before --
is left exactly as it is and the pack's places are added beneath it; one that
was deleted, deliberately, is not brought back, and nothing under it is
loaded. A PIN code already held anywhere is left where it is. So loading the
same states twice, or a newer pack, adds only what is new.

Geography carries no firm: what is loaded is per store, shared by every firm
on it.
"""

from __future__ import annotations

import csv
import gzip
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.sales.models import (
    GeoCity,
    GeoCountry,
    GeoDistrict,
    GeoLocality,
    GeoPostalCode,
    GeoState,
)

PACK = Path(__file__).resolve().parents[1] / "data" / "india_post_pincodes.csv.gz"
SOURCE = (
    "India Post, All India Pincode Directory (data.gov.in), Government Open "
    "Data Licence - India"
)

#: The states a firm is offered ticked: the owner's first market (B6, 2026-10-02).
DEFAULT_STATES = ("AP", "TS", "KA", "TN", "KL", "PY", "LD")

#: Office types that deliver for a PIN code, best first. A branch office (BO)
#: names a village, so it names the town only where nothing else does.
_DELIVERING = {"HO": 0, "PO": 1, "SO": 1}

_SUFFIX = re.compile(
    r"\s+(?:B\.?\s?O|S\.?\s?O|H\.?\s?O|P\.?\s?O|G\.?\s?P\.?\s?O)\.?$", re.I
)


@dataclass(frozen=True, slots=True)
class _Office:
    """One row of the pack."""

    district: str
    pincode: str
    office: str
    kind: str


@dataclass(slots=True)
class StateLoad:
    """What loading one state added and what it left alone."""

    code: str
    name: str
    districts: int = 0
    cities: int = 0
    postal_codes: int = 0
    localities: int = 0
    skipped: int = 0
    #: Why nothing was loaded, where nothing was.
    note: str | None = None


@dataclass(slots=True)
class PlacesLoad:
    """The outcome of one load, state by state."""

    states: list[StateLoad] = field(default_factory=list)


def place_name(office: str) -> str:
    """Return an office's place name: ``Kothimir B.O`` -> ``Kothimir``."""
    return _SUFFIX.sub("", office.strip()).strip() or office.strip()


def district_name(raw: str) -> str:
    """Return India Post's upper-case district as it reads on an address."""
    return " ".join(word.capitalize() for word in raw.split())


@lru_cache(maxsize=1)
def _pack() -> dict[str, list[_Office]]:
    """Return the pack's offices by state code, read once per process."""
    if not PACK.exists():
        return {}
    by_state: dict[str, list[_Office]] = defaultdict(list)
    with gzip.open(PACK, "rb") as handle:
        for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8")):
            by_state[row["state"]].append(
                _Office(
                    district=row["district"],
                    pincode=row["pincode"],
                    office=row["office"],
                    kind=row["type"].upper(),
                )
            )
    return dict(by_state)


def _code(name: str, taken: set[str]) -> str:
    """Return a code for a place, unique among its siblings (max 20 chars)."""
    base = re.sub(r"[^A-Z0-9]", "", name.upper())[:20] or "PLACE"
    code, counter = base, 1
    while code in taken:
        counter += 1
        suffix = str(counter)
        code = base[: 20 - len(suffix)] + suffix
    taken.add(code)
    return code


class PlacesPackService:
    """Offer the pack's states and load the ones a firm chooses."""

    def __init__(self, session: Session) -> None:
        """Keep the store session the places are loaded into."""
        self._session = session
        self._fresh: dict[str, tuple[UUID, set[str]]] = {}

    def summary(self) -> list[dict[str, object]]:
        """Return each state in the pack: its size and how much is loaded.

        A state the store does not hold, or holds only deleted, cannot be
        loaded and says so.
        """
        states = self._states()
        loaded: dict[UUID, int] = dict(
            self._session.execute(
                select(GeoDistrict.state_id, func.count())
                .where(GeoDistrict.is_deleted.is_(False))
                .group_by(GeoDistrict.state_id)
            )
            .tuples()
            .all()
        )
        result: list[dict[str, object]] = []
        for code, offices in sorted(_pack().items()):
            state = states.get(code)
            result.append(
                {
                    "code": code,
                    "name": state.name if state else code,
                    "available": state is not None,
                    "post_offices": len(offices),
                    "postal_codes": len({office.pincode for office in offices}),
                    "districts": len({office.district for office in offices}),
                    "districts_held": int(loaded.get(state.id, 0)) if state else 0,
                    "default": code in DEFAULT_STATES,
                }
            )
        return result

    def load(self, codes: list[str], *, actor_id: UUID) -> PlacesLoad:
        """Load the chosen states, skipping what the store already holds.

        Raises:
            ValidationError: When no state is named, one is not in the pack,
                or the pack is missing from this installation.

        """
        wanted = [code.strip().upper() for code in codes if code.strip()]
        if not wanted:
            raise ValidationError("Choose at least one state to load.")
        pack = _pack()
        if not pack:
            raise ValidationError(
                "The places file is missing from this installation; reinstall "
                "or ask your supplier for it."
            )
        unknown = [code for code in wanted if code not in pack]
        if unknown:
            raise ValidationError(f"Not in the places file: {', '.join(unknown)}.")
        states = self._states()
        outcome = PlacesLoad()
        # PIN codes this load created, with their localities: a PIN that
        # crosses a district or state border gets the other side's offices
        # as localities rather than losing them.
        self._fresh = {}
        for code in dict.fromkeys(wanted):
            state = states.get(code)
            if state is None:
                outcome.states.append(
                    StateLoad(
                        code=code,
                        name=code,
                        note="This store holds no such state, or it was deleted.",
                    )
                )
                continue
            outcome.states.append(
                self._load_state(state, pack[code], actor_id=actor_id)
            )
        self._session.flush()
        record_audit(
            self._session,
            action="sales_territory.geo.places_loaded",
            entity_type="geo_state",
            entity_id=next(
                (
                    states[item.code].id
                    for item in outcome.states
                    if item.code in states
                ),
                actor_id,
            ),
            actor_id=actor_id,
            after_data={
                "source": SOURCE,
                "states": [
                    {
                        "code": item.code,
                        "districts": item.districts,
                        "cities": item.cities,
                        "postal_codes": item.postal_codes,
                        "localities": item.localities,
                        "skipped": item.skipped,
                    }
                    for item in outcome.states
                ],
            },
        )
        return outcome

    # ------------------------------------------------------------------

    def _states(self) -> dict[str, GeoState]:
        """Return India's live states by code."""
        india = self._session.scalar(
            select(GeoCountry.id).where(
                func.upper(GeoCountry.code).in_(["IN", "IND"]),
                GeoCountry.is_deleted.is_(False),
            )
        )
        statement = select(GeoState).where(GeoState.is_deleted.is_(False))
        if india is not None:
            statement = statement.where(GeoState.country_id == india)
        return {row.code.upper(): row for row in self._session.scalars(statement)}

    def _load_state(
        self, state: GeoState, offices: list[_Office], *, actor_id: UUID
    ) -> StateLoad:
        """Add one state's districts, towns, PIN codes and localities."""
        report = StateLoad(code=state.code, name=state.name)
        audit = {"created_by": actor_id, "updated_by": actor_id}

        # Districts: the store's own by name, deleted ones included.
        held = {
            row.name.casefold(): row
            for row in self._session.scalars(
                select(GeoDistrict).where(GeoDistrict.state_id == state.id)
            )
        }
        codes = {row.code for row in held.values() if not row.is_deleted}
        by_district: dict[str, list[_Office]] = defaultdict(list)
        for office in offices:
            by_district[district_name(office.district)].append(office)
        district_ids: dict[str, UUID] = {}
        new_districts: list[dict[str, object]] = []
        for name, _rows in sorted(by_district.items()):
            existing = held.get(name.casefold())
            if existing is not None:
                if existing.is_deleted:
                    report.skipped += 1
                    continue
                district_ids[name] = existing.id
                continue
            district_id = uuid4()
            new_districts.append(
                {
                    "id": district_id,
                    "state_id": state.id,
                    "code": _code(name, codes),
                    "name": name[:100],
                    "is_active": True,
                    **audit,
                }
            )
            district_ids[name] = district_id
        if new_districts:
            self._session.execute(insert(GeoDistrict), new_districts)
        report.districts = len(new_districts)

        # PIN codes held anywhere in the store, live or deleted: a PIN is one
        # place nationally, and a firm's own entry or deletion stands.
        pins_held = set(self._session.scalars(select(GeoPostalCode.postal_code))) - set(
            self._fresh
        )
        cities_held: dict[UUID, dict[str, GeoCity]] = defaultdict(dict)
        for row in self._session.scalars(
            select(GeoCity).where(GeoCity.district_id.in_(list(district_ids.values())))
        ):
            cities_held[row.district_id][row.name.casefold()] = row
        city_codes: dict[UUID, set[str]] = defaultdict(set)
        for district_id, rows in cities_held.items():
            city_codes[district_id] = {
                row.code for row in rows.values() if not row.is_deleted
            }

        new_cities: list[dict[str, object]] = []
        new_pins: list[dict[str, object]] = []
        new_localities: list[dict[str, object]] = []
        for name, offices_here in sorted(by_district.items()):
            target = district_ids.get(name)
            if target is None:
                continue
            by_pin: dict[str, list[_Office]] = defaultdict(list)
            for office in offices_here:
                by_pin[office.pincode].append(office)
            for pincode, pin_offices in sorted(by_pin.items()):
                if pincode in self._fresh:
                    pin_id, seen = self._fresh[pincode]
                    self._localities(pin_id, pin_offices, seen, new_localities, audit)
                    continue
                if pincode in pins_held:
                    report.skipped += 1
                    continue
                main = min(
                    pin_offices,
                    key=lambda item: (_DELIVERING.get(item.kind, 9), item.office),
                )
                town = place_name(main.office)[:100]
                city = cities_held[target].get(town.casefold())
                if city is not None and city.is_deleted:
                    report.skipped += 1
                    continue
                if city is None:
                    city_id = uuid4()
                    new_cities.append(
                        {
                            "id": city_id,
                            "district_id": target,
                            "code": _code(town, city_codes[target]),
                            "name": town,
                            "is_active": True,
                            **audit,
                        }
                    )
                    placeholder = GeoCity(id=city_id, name=town, is_deleted=False)
                    cities_held[target][town.casefold()] = placeholder
                    city = placeholder
                pin_id = uuid4()
                new_pins.append(
                    {
                        "id": pin_id,
                        "city_id": city.id,
                        "postal_code": pincode,
                        "is_active": True,
                        **audit,
                    }
                )
                self._fresh[pincode] = (pin_id, set())
                self._localities(
                    pin_id, pin_offices, self._fresh[pincode][1], new_localities, audit
                )
        batches: list[tuple[type[object], list[dict[str, object]]]] = [
            (GeoCity, new_cities),
            (GeoPostalCode, new_pins),
            (GeoLocality, new_localities),
        ]
        for model, values in batches:
            for start in range(0, len(values), 5000):
                self._session.execute(insert(model), values[start : start + 5000])
        report.cities = len(new_cities)
        report.postal_codes = len(new_pins)
        report.localities = len(new_localities)
        return report

    @staticmethod
    def _localities(
        pin_id: UUID,
        offices: list[_Office],
        seen: set[str],
        into: list[dict[str, object]],
        audit: dict[str, UUID],
    ) -> None:
        """Add each office under a PIN as a locality, once by name."""
        for entry in sorted(offices, key=lambda item: item.office):
            locality = place_name(entry.office)[:120]
            if locality.casefold() in seen:
                continue
            seen.add(locality.casefold())
            into.append(
                {
                    "id": uuid4(),
                    "postal_code_id": pin_id,
                    "name": locality,
                    "is_active": True,
                    **audit,
                }
            )
