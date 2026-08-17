# Territory, Routes & Beats

How a distributor draws a round, puts shops on it in the order they are called,
says which days it runs, and gets a sale filed against it.

Verified against the running backend and the seeded WHOLE01 firm on 2026-08-16.
Every count and behaviour below was read from the API or the database, not
remembered.

## The idea

A **territory** is one node in a firm-configurable tree. A node becomes a
**route** — a round somebody walks — by carrying a *route profile*. Shops are
assigned to a node and given a **call order**. A **beat plan** says which days
that route runs. Put together, they answer "who does Ravi call on Monday, in
what order", and they tag every sale so the by-territory, by-route and
by-salesman reports have something to group.

```
sales_hierarchy_configs        one per firm: max levels, the multi-route flags
  └ sales_hierarchy_levels     Region / Territory / Route — named by the firm

sales_territories              every node at every level; parent_id + path
  ├ territory_route_profiles   1:1 — the row that makes a node a ROUTE
  │   └ territory_working_days weekday 1..7
  ├ territory_customer_assignments   shop ⇄ node, with visit_sequence
  └ territory_salesman_assignments   user ⇄ node, is_primary, include_children

sales_route_types              the kinds of round: SALES, COLLECTION, …
sales_beat_plans               when a route runs: WEEKLY / FORTNIGHTLY / MONTHLY / CUSTOM
  └ sales_beat_plan_customer_stops   optional: the outlets of one day-beat

geo_countries → geo_states → geo_districts → geo_cities
  → geo_postal_codes → geo_localities        shared reference data
address_masters                reusable multi-address storage (no client yet)
```

Seventeen tables, one router (`app/sales/api/router.py`, 63 endpoints), one
service (`app/sales/services/territory_service.py`) plus the small
`scope_resolution.py` that five other modules call.

## The hierarchy is configuration

Levels are rows, not an enum. `SalesHierarchyLevel` carries `level_order`,
`level_code`, `display_name` and `is_mandatory`; the demo firms run
`Region > Territory > Route`. `PUT /hierarchy-levels` is platform-admin.

A node may only be created at the top level or under a parent one level above
it, and `path` is maintained as a `/`-joined string of codes. Moving a node
repaths its descendants.

## A route is a node with a profile

`TerritoryRouteProfile` is what separates a round from a zone. It carries the
route type, the visit frequency, the working days, an **effective window**, and
optional city/postal/locality links.

**The effective window is enforced**, as of 2026-08-16. `effective_from` /
`effective_to` had been stored since the first migration and read nowhere —
unlike UOM conversion rules and tax profiles, both of which filter on theirs —
so a round "effective until June" still ran in August. Because there is exactly
one profile per node (`UQ_territory_route_profiles_territory`), the window means
**when the round operates**, not a version of a profile. It now decides two
things:

- a beat plan does not call a route outside its window, and says so;
- `resolve_sales_scope` will not tag a document with a route that was not
  running on the document's own date.

The territory still applies in that second case. The shop is on it either way;
the window describes the round.

## Customers on a round

`TerritoryCustomerAssignment` is the shop ⇄ node row. Three rules, each keyed in
the database as of `20260816_0092`:

| Rule | Key | Why |
| --- | --- | --- |
| one row per (route, shop), among live rows | `…_pair_active` | a retired assignment used to reserve that shop for that round forever |
| one **primary** round per shop | `…_primary_active` | `resolve_sales_scope` finds exactly one primary to decide which round a sale counts against; two resolved to nothing and the sale appeared in no report at all |
| one shop per **stop number** on a round | `…_sequence_active` | two outlets could both be stop 1, and the call list fell back to a `created_at` tiebreak — an order nobody chose |

**A shop may be on several rounds.** A distributor calls the same outlet on a
sales beat and a collection round; that is ordinary. The first round it joins
takes the primary flag, and later ones do not.

**`PUT /{id}/customers` replaces the whole list**, and `visit_sequence` is
position in it, so membership and order travel together. Two consequences worth
knowing before writing a client:

- Omitting `is_primary` means *leave it alone*. Sending it back would demote the
  round somebody chose, and collides with the primary key above the moment a
  shop is on two rounds. `TerritoryCustomerAssignmentRecord.toJson` on the
  desktop deliberately omits it.
- The service **releases the stop numbers it is about to reassign, flushes, then
  hands out the new ones**. The sequence key is checked per statement and a
  partial index cannot be `DEFERRABLE`, so reassigning row by row collided the
  instant two shops swapped places — which is exactly what dragging one above
  another does. Only the numbers actually moving are released: a re-save that
  says nothing about order must leave every sequence where it was.

## Beat plans and the call list

A plan targets a **route** — never a Region, which would read as a schedule for
a whole state and call nobody. `WEEKLY` and `FORTNIGHTLY` need a weekday,
`MONTHLY` a weekday and a week-of-month, `CUSTOM` is not computed.

`GET /call-lists?date=&salesman_id=` and
`GET /beat-plans/{id}/call-list?date=` answer who should be called. Both are
**computed, never stored**: materialising occurrences would need a regeneration
story every time a plan, a route or an assignment changed, and a stale list
sends somebody to the wrong shop. The date defaults to `utc_now().date()`.

A plan that cannot be computed **says so** rather than returning an empty list —
"nobody to call today" and "this cannot be worked out" are different answers,
and one blank screen for both misreports one of them. A fortnightly plan with no
`starts_on` has no anchor to count every-other-week from and reports that
instead of guessing.

Stops resolve in this order: the plan's own outlet stops, else the customers on
the plan's territory in `visit_sequence` order. `sales_beat_plan_stops` — which
named a *sub-territory* as a stop and needed a hierarchy level below the route
that no firm here has — was dropped in `20260816_0093`.

## How a sale gets filed against a round

`sales_orders`, `sales_invoices` and `delivery_notes` carry `territory_id`,
`route_id` and `salesman_id`; quotations and sales returns carry the first and
last. **Nothing populated them until 2026-08-16** — every seeded order had all
three NULL and `/reports/by-territory`, `/reports/by-route` and
`/reports/by-salesman` answered `[]` from endpoints that were themselves
correct.

`app/sales/services/scope_resolution.py` resolves them server-side, so the
desktop, a direct API call and the seeder are all covered by one rule. It is a
plain function, not a service method: five domains call it and importing
`SalesTerritoryService` into each would make a cycle.

- **What a caller sends is validated, never overridden.** A territory the
  customer is not assigned to is refused; so is a salesperson who does not cover
  it.
- **What a caller leaves blank is derived — and derivation refuses to guess.** A
  shop on two rounds with no primary resolves to nothing. A report full of
  plausible rows is worse than an empty one.
- **Conversion paths are left alone.** Delivery notes take all three from the
  order; invoices and returns only fill blanks. A customer moved to another
  round last week must not retag the order they placed last month.

## Geography is shared, and only reference data

Country → state → district → city → postal code → locality. Not firm-owned: one
row serves every firm in a store. Reads need `TERRITORY_VIEW`; **writes are
platform-admin**.

Deleting one is refused while anything still points at it — a child level, an
address, a branch, a warehouse or a route profile. Every foreign key into these
tables is `ondelete="RESTRICT"`, which *looks* like the guard is already there
and is not: these rows are soft-deleted, and a soft delete never reaches the
database's referential check. A "deleted" city would stay wired to every branch
naming it and simply vanish from the list.

**Customer addresses reference these tables as of 2026-08-16.**
`customer_addresses` carries `country_id`, `state_id`, `district_id`,
`city_id`, `postal_code_id` and `locality_id` beside the free text it always
had (`20260816_0094`). All four address-carrying modules — customers, vendors,
branches and warehouses — now name the same masters, which is what makes
"Parrys" one place rather than one spelling of it, and is the prerequisite for
putting a coordinate anywhere.

Two rules follow.

- **The keys are the truth and the text is derived from them.** `city`,
  `state`, `country` and `postal_code` are NOT NULL and every report reads
  them, so they stay; `CustomerService._apply_place` rewrites them from
  whichever masters are named, and refuses an address whose rungs do not
  belong together. An address that names no place keeps the text it was given,
  which is what every client written before these columns did.
- **The columns are nullable and stay nullable.** They were added to a table
  with live rows, a firm may have no masters at all, and the migration's
  backfill only claims a match it is sure of — one live master row, compared
  case-insensitively, anchored to the rung above or unique across the store.
  Where the seeded data disagreed with the masters (a store whose only state
  is "Andera Pradesh" while its addresses are in Telangana) it filled nothing,
  which is the intended outcome: a guess here is indistinguishable from a fact
  afterwards.

The Route Builder's pin-code search still matches the text. Moving it onto
`postal_code_id` is the natural follow-up now that the key exists.
`address_masters` remains unused and is due for retirement.

## Permissions

Nine codes, all seeded: `TERRITORY_VIEW`, `_CREATE`, `_UPDATE`, `_DELETE`,
`_RESTORE`, `_ASSIGN_CUSTOMERS`, `_ASSIGN_SALESMEN`, `_IMPORT`, `_EXPORT`.
Hierarchy-level editing and every geography write are guarded by the
platform-admin designation rather than a code.

## The desktop

Six tabs on the Sales workspace, declared in `ui/workspace/module_catalog.dart`
and dispatched in `ui/desktop_shell.dart`:

| Tab | What it is for |
| --- | --- |
| **Geography** | the tree, the editor, and a full-screen detail dialog per node |
| **Route Types** | the kinds of round, as a `ResourceDefinition` |
| **Beat Plans** | when each route runs |
| **Call Lists** | who is called on a date, read-only |
| **Coverage** | how much ground each salesperson carries, and who carries none |
| **Route Builder** | lay out a beat by pin code or street, for outlets you do not know by name |
| **Places** | the geography ladder; read-only unless platform admin |

A customer's own rounds appear on the **Routes** tab of the customer dialog:
the relationship used to be one-directional, listable only from the territory.

`TerritoryDetailDialog` draws a round **one stop at a time**: clicking an outlet
appends it as the next stop, first is START and last is END, and clicking one
already on the path removes it and closes the gap. Dragging corrects a mis-click.

Two client rules that are not obvious and have both already caused defects:

- **Never ask for a page larger than `maxApiPageSize` (100).** The routers that
  build their `PaginationParams` by hand answered a 500 rather than a message
  naming the limit, and two screens shipped asking for 500 — both broken against
  every real backend while their tests, whose fakes ignore `pageSize`, stayed
  green. Use `fetchAllPages` from `ui/workspace/paged_fetch.dart`.
- **A screen that replaces a whole list must prove it loaded that list first.**
  Both the Route Builder and the detail dialog clear the pane *before* the read
  rather than after it succeeds, and refuse to save until the pane provably
  holds the selected route. Without that, a failed read left the previous
  route's shops on screen and one Save wrote them over a different round.

## Tests

Backend, all under `backend/tests/unit/` — **84 tests across eight files**:

| File | Covers |
| --- | --- |
| `test_sales_territory_route_management` | hierarchy, tree, CRUD, scope and permissions |
| `test_sales_territory_beat_plans` | route types, beat plans, call order, the primary flag, the swap |
| `test_sales_call_lists` | recurrence, the reasons, the effective window |
| `test_sales_scope_resolution` | what a document is tagged with, and what it refuses to guess |
| `test_sales_assignable_customers` | search by pin code and street; unassigned-only |
| `test_sales_geography_masters` | edit, retire, the in-use guard, the audit trail |
| `test_sales_territory_bulk_operations` | the four bulk operations and their one transaction |
| `test_sales_territory_policies` | the four hierarchy settings, the prospect flag, the import transaction, a customer's rounds |

Desktop, in `desktop/test/` — **59 widget tests across eight files**, one per
screen plus `territory_route_test` for the editor.

## Migrations

| Revision | What |
| --- | --- |
| `20260816_0090` | `sales_beat_plan_customer_stops` — outlets on a plan |
| `20260816_0091` | geography keys scoped to live rows, so a retired place releases its code |
| `20260816_0092` | the three customer-assignment keys, with a backfill that repairs rather than fails |
| `20260816_0093` | drop `sales_beat_plan_stops`, refusing if any store holds rows |

All four touch **firm-owned** tables. Run `scripts/migrate_all_stores.py --yes`,
never a bare `alembic upgrade head`.

## Where this stands

Measured against the SFA/DMS systems distributors actually run — Bizom,
FieldAssist, Botree, SAP Route-to-Market, Salesforce Maps:

| Capability | Us | Those systems |
| --- | --- | --- |
| Configurable territory hierarchy | ✅ | ✅ |
| Route / beat master, route types | ✅ | ✅ |
| Outlet→beat mapping with call sequence | ✅ | ✅ |
| Beat plan (PJP): weekly / fortnightly / monthly | ✅ | ✅ + cyclic day-N |
| Call list for a date | ✅ | ✅ |
| Sales tagged to territory / route / salesman | ✅ | ✅ |
| Bulk reorganisation, CSV import | ✅ | ✅ |
| Salesman coverage | ✅ | ✅ |
| Outlet classification driving frequency | ❌ | ✅ |
| Beat KPIs — coverage %, TC/PC, adherence | ❌ | ✅ core |
| Visit execution — check-in, outcome, order at stop | ❌ | ✅ core |
| Geocoding, map view, route optimisation | ❌ planned | ✅ |
| Targets vs achievement by route | ❌ | ✅ |
| Mobile field client | ❌ | ✅ |

**The planning half is competitive; the execution half does not exist.** This is
a route *planner*, not a field-force system, and the absences below are
decisions rather than oversights.

## Not built, in dependency order

**Addresses are structured now, which is what coordinates were waiting for.**
Done on 2026-08-16: all four address-carrying modules name the geography
masters, and `customer_addresses` was migrated (see above). **No table stores a
latitude or longitude yet** — but there is now somewhere to put one that groups
by locality rather than by spelling. The remaining work is the columns, a
geocoding source, and moving the Route Builder's pin-code search off the text
and onto `postal_code_id`.

**Outlet classification** — A/B/C class and channel (GT / MT / HoReCa) on the
customer, with visit frequency derived from class. `customer_type` is a broad
type, not a segmentation. It is what would make the KPIs below mean something.

**Beat KPIs** — coverage %, Total Calls / Productive Calls, strike rate, lines
per call, drop size, beat adherence. Every SFA reports these; most need visit
execution to have real numbers rather than planned ones.

**Visit execution** — check-in / check-out per stop, outcome,
reason-for-no-order, order raised at the stop. The largest gap, and the thing
that turns a plan into a field-force system. Wants a mobile client.

**Map view and route optimisation**, then **targets vs achievement** by
territory, route and salesman.

**Smaller** — cyclic day-N beat plans; a distributor dimension on a route; leave
and holiday rescheduling; territory ownership history; the `salesman` →
`salesperson` rename across model, API and permission codes; geography's two
competing retire flags (`is_active` and soft delete, where the lists filter only
the second, so an inactive country still appears).
