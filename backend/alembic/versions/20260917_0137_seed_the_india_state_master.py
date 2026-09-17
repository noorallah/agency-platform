"""Seed the 28 Indian states and 8 union territories into every firm store.

Revision ID: 20260917_0137
Revises: 20260914_0136
Create Date: 2026-09-17

Geography is a **per-store** master -- `geo_countries` and `geo_states` carry no
`firm_id`, so every firm sharing a store shares one copy -- and it shipped with
nothing in it. Counted across this project's own stores on 2026-09-17: every
one held India, because `gst_template.py` creates the country where a store has
none, and **three of seven held no states at all**. The State rung of the place
picker on customers, vendors, branches and warehouses was empty until somebody
typed a state in by hand, and every firm rebuilt the same list independently.

That matters most on a fresh installation, which is the case this was written
for: a customer installs the product, creates their first firm, and has to
invent the Indian state master before they can record a customer's address.

**States only.** Districts, cities, postal codes and localities stay
user-entered: the full Indian dataset is large, volatile, and nobody needs all
of it, while the state list is small, stable, and the rung an address actually
turns on.

**No GST state codes here**, despite the backlog asking for them. They are not
missing from this seed by oversight -- there is nowhere to put them and nothing
that would read them. `geo_states` has only `country_id`, `code`, `name` and
`is_active`, and every place-of-supply decision in this codebase reads the
numeric code off the **GSTIN**: `einvoice/services/payload.py::_state_code`
takes the first two digits, and `gst_returns` does the same, with the comment
"reading it off the number rather than off an address field means the two can
never disagree". Geography is not in that path. A `gst_state_code` column would
be a new column and a second source for a fact already derived.

So `code` here is the two-letter abbreviation this repository already uses --
`TN`, `KA`, `TS` in the sample-data blueprint, `TN` and `AP` in the live stores.

Three things about how it writes, each of which is a rule this repository has
already paid for:

* **`sa.table` stubs, never the ORM models.** A migration is a record of one
  change on one date; reading today's models would make a replay next year do
  whatever they say then, which is a different change wearing this revision id.
* **A `has_table` guard**, because the platform schema holds identity and the
  firm registry and none of the firm-owned tables. Without it this fails there.
* **It skips, rather than merges.** A state whose code *or* name is already in
  the store is left exactly as it is -- including a soft-deleted one. Both
  unique indexes are scoped to `is_deleted = false`, so re-inserting a deleted
  state would succeed and quietly undo a deliberate deletion. A store that has
  already typed its own list keeps it; this only fills a gap.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0137"
down_revision: str | None = "20260914_0136"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_COUNTRIES = sa.table(
    "geo_countries",
    sa.column("id", sa.Uuid()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("iso2", sa.String()),
    sa.column("iso3", sa.String()),
    sa.column("phone_code", sa.String()),
    sa.column("is_deleted", sa.Boolean()),
)

_STATES = sa.table(
    "geo_states",
    sa.column("id", sa.Uuid()),
    sa.column("country_id", sa.Uuid()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)

#: India, spelled exactly as `app/tax/services/gst_template.py` spells it, so a
#: store that has had the tax template applied and one that has only had this
#: migration hold the same row rather than two that differ in a field.
_INDIA = {
    "code": "IN",
    "name": "India",
    "iso2": "IN",
    "iso3": "IND",
    "phone_code": "91",
}

#: The 28 states and 8 union territories, as constituted after the 2019-2020
#: reorganisations: Jammu and Kashmir and Ladakh are separate union
#: territories, and Dadra and Nagar Haveli and Daman and Diu is the single
#: merged one. Codes are the two-letter abbreviations already used in
#: `scripts/generate_sample_data.py`'s blueprint and in the live stores.
_INDIAN_STATES: tuple[tuple[str, str], ...] = (
    # States (28)
    ("AP", "Andhra Pradesh"),
    ("AR", "Arunachal Pradesh"),
    ("AS", "Assam"),
    ("BR", "Bihar"),
    ("CG", "Chhattisgarh"),
    ("GA", "Goa"),
    ("GJ", "Gujarat"),
    ("HR", "Haryana"),
    ("HP", "Himachal Pradesh"),
    ("JH", "Jharkhand"),
    ("KA", "Karnataka"),
    ("KL", "Kerala"),
    ("MP", "Madhya Pradesh"),
    ("MH", "Maharashtra"),
    ("MN", "Manipur"),
    ("ML", "Meghalaya"),
    ("MZ", "Mizoram"),
    ("NL", "Nagaland"),
    ("OD", "Odisha"),
    ("PB", "Punjab"),
    ("RJ", "Rajasthan"),
    ("SK", "Sikkim"),
    ("TN", "Tamil Nadu"),
    ("TS", "Telangana"),
    ("TR", "Tripura"),
    ("UP", "Uttar Pradesh"),
    ("UK", "Uttarakhand"),
    ("WB", "West Bengal"),
    # Union territories (8)
    ("AN", "Andaman and Nicobar Islands"),
    ("CH", "Chandigarh"),
    ("DH", "Dadra and Nagar Haveli and Daman and Diu"),
    ("DL", "Delhi"),
    ("JK", "Jammu and Kashmir"),
    ("LA", "Ladakh"),
    ("LD", "Lakshadweep"),
    ("PY", "Puducherry"),
)


def upgrade() -> None:
    """Fill in whatever of the India state master this store is missing."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # The platform schema holds identity, RBAC and the firm registry, and none
    # of the firm-owned tables. Geography is firm-owned.
    if not inspector.has_table("geo_countries") or not inspector.has_table(
        "geo_states"
    ):
        return

    country_id = _india_id(bind)
    if country_id is None:
        country_id = uuid4()
        bind.execute(_COUNTRIES.insert().values(id=country_id, **_INDIA))

    # Read both keys, and read them including soft-deleted rows. The unique
    # indexes are scoped to `is_deleted = false`, so a deleted 'MH' would not
    # refuse a second one -- the store would simply end up with a state
    # somebody removed on purpose, back again and duplicated underneath.
    taken_codes: set[str] = set()
    taken_names: set[str] = set()
    for code, name in bind.execute(
        sa.select(_STATES.c.code, _STATES.c.name).where(
            _STATES.c.country_id == country_id
        )
    ).all():
        taken_codes.add((code or "").strip().upper())
        taken_names.add((name or "").strip().casefold())

    missing = [
        {
            "id": uuid4(),
            "country_id": country_id,
            "code": code,
            "name": name,
            "is_active": True,
            "is_deleted": False,
        }
        for code, name in _INDIAN_STATES
        if code not in taken_codes and name.casefold() not in taken_names
    ]
    if missing:
        op.bulk_insert(_STATES, missing)


def _india_id(bind: sa.engine.Connection) -> object | None:
    """Return this store's India, by code and then by name.

    Two lookups because `gst_template.py` uses the same pair: a store seeded by
    an older script may carry the name without the code this expects, and
    creating a second India would take the country unique index with it.
    """
    found = bind.execute(
        sa.select(_COUNTRIES.c.id).where(
            _COUNTRIES.c.code == _INDIA["code"],
            _COUNTRIES.c.is_deleted.is_(False),
        )
    ).scalar()
    if found is not None:
        return found
    return bind.execute(
        sa.select(_COUNTRIES.c.id).where(
            _COUNTRIES.c.name == _INDIA["name"],
            _COUNTRIES.c.is_deleted.is_(False),
        )
    ).scalar()


def downgrade() -> None:
    """Keep the seeded places.

    Nothing here can tell a seeded state from one a firm typed, and by the time
    anybody downgrades, addresses, customers and territories may point at these
    rows. Deleting reference data on the way down would take live records with
    it to undo a change that only ever added rows.
    """
