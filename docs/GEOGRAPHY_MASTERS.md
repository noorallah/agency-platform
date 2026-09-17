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

**Only states.** Districts, cities, postal codes and localities stay
user-entered -- the full Indian dataset is large and volatile, while the state
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
