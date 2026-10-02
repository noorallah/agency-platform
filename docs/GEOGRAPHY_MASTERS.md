# Geography masters and the area picker

Moved out of `CLAUDE.md` on 2026-09-15, when that file passed the 150k-character
limit. Verbatim; the imperative half stays in `CLAUDE.md` with a pointer here.

**Geography is one set of masters, and all four address-carrying modules name it.** `geo_countries` → `geo_states` → `geo_districts` → `geo_cities` → `geo_postal_codes` → `geo_localities`, per firm store. Customers, vendors, branches and warehouses each carry the six keys; `GeoAreaPicker` (`desktop/lib/ui/workspace/geo_area_picker.dart`) is the one control that fills them, so use it rather than a fifth copy of the cascade. **Customers are the odd one out and the reason there is a migration**: they had free text and no keys, where the other three had keys and no form. `20260816_0094` added the keys beside the text and backfilled only unambiguous matches. **The keys are the truth; the text is derived from them** by `CustomerService._apply_place`, because `city`, `state`, `country` and `postal_code` are NOT NULL and every report reads them -- a row whose `city` says one thing and whose `city_id` says another leaves nothing to say which a report should believe. An address naming no place keeps the text it was given. Two traps in the picker itself, both found by testing rather than by reading: a stored id that is not in the loaded list must stay as an item of its own, or `DropdownButtonFormField` asserts and the form saves as blank; and a rung must be loaded from the *new* selection rather than from `widget.value`, which the parent has not rebuilt yet in the frame the choice was made -- choosing a country loaded no states at all, and shipped that way because the first two screens' tests only ever chose one rung.

## What a store starts with

**The India state master is seeded into every store by `20260917_0137`** -- the
28 states and 8 union territories, plus India itself where a store has none.
Before that, geography shipped with nothing in it: on 2026-09-17 every store
held India (because `gst_template.py` creates the country where a store lacks
one) and **three of seven held no states at all**, so the State rung of the
picker was blank until somebody typed one in, and every firm rebuilt the same
list independently.

Geography carries **no `firm_id`**, so this is per *store* rather than per
firm: firms sharing `firm_shared` share one copy, and a dedicated store gets
its own when `upgrade_store` runs during provisioning.

**Only states are seeded.** Districts, cities, postal codes and localities are
loaded on request from the India Post pack (below) or typed in -- the full Indian dataset is large and volatile, while the state
list is small, stable and the rung an address actually turns on.

**`code` is the two-letter abbreviation** (`TN`, `KA`, `MH`), which is what the
sample-data blueprint and the live stores already used. It is deliberately
**not** the numeric GST state code: `geo_states` has no column for one, and
nothing would read it if it did. Place of supply is derived from the **GSTIN**
-- `einvoice`'s `_state_code` takes the first two digits and `gst_returns` does
the same -- precisely so the number and the address cannot disagree. Geography
is not in that path.

**The seed skips; it never merges.** A state whose code *or* name a store
already holds is left exactly as it is, soft-deleted ones included. Both unique
indexes are scoped to `is_deleted = false`, so re-inserting a deleted state
would succeed and quietly undo a deliberate deletion -- a firm that removed a
place it does not trade in would find it back after the next upgrade.

## Loading places from India Post (decision B6, 2026-10-02)

**Districts, towns, PIN codes and localities can be loaded by state** from the
India Post *All India Pincode Directory* (data.gov.in, Government Open Data
Licence - India), which ships with the server as
`backend/app/sales/data/india_post_pincodes.csv.gz` -- five columns of the
source, gzipped, all 36 states and territories, 1.1 MB. Nothing is fetched
from the internet. `scripts/build_places_pack.py <source.csv>` rebuilds it
when India Post republishes; `packaging/nuitka.args` carries it into the
compiled build (`--include-package-data=app.sales`).

- **The screen offers every state and ticks the southern ones** (AP, TS, KA,
  TN, KL, PY, LD -- the first market). `GET /sales-territories/geo/places-pack`
  lists them; `POST /geo/places-pack/load` loads, platform administrator only
  like every other geography write.
- **India Post has no town column**, so a PIN code's town is its delivering
  office -- head office first, then sub-office, a village branch only where
  nothing else serves the PIN -- with the ` H.O` / ` S.O` / ` B.O` suffix
  dropped, and every office under the PIN, branches included, is a locality.
  Districts read in title case (`Kumuram Bheem Asifabad`).
- **Skip, never merge.** A district or town the store holds by name is kept
  as it is and filled beneath; a deleted one is not brought back and nothing is
  loaded under it; a PIN code held anywhere before the load is left where it
  is. Loading twice adds nothing twice. A PIN that crosses a district or state
  border **within one load** gets the other side's offices as localities of
  the PIN already created.
- **The southern states come with the build** (owner, 2026-10-02). Migration
  `20261002_0231` runs the same loader (`initialise_store`) on every firm
  store as it is migrated -- the installer's `migrate-all`, an upgrade, and a
  new firm's provisioning -- so nobody has to press the button for the first
  market. The platform store is skipped. Other states, or a newer pack, stay
  on the screen. On PostgreSQL it adds about nine seconds to each store's
  first migration past that revision.
- **Per store.** All seven southern states are 129 districts, 6,802 PIN codes
  and 43,475 localities, about three seconds.

## Retiring a place

Deleting a place is a soft delete, so the `RESTRICT` foreign keys into these
tables never fire; `_assert_geo_unused` in `territory_service.py` is the guard.
It refuses while anything live still names the place, and the refusal names
what: the level below, address masters, branches, warehouses, route profiles,
**customer and vendor addresses** (of a live customer or vendor only) and, for a
country, **tax systems, tax country mappings and tax rules**. The addresses are
the ones that matter most: a customer or vendor save resends its stored places,
and a retired place is refused as unknown, so retiring one an address stands on
would leave that record impossible to save (D-CFG-12). The tax rule execution
log is deliberately not counted -- it is history, and retention prunes it.
