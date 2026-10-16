# Screen cases, the firm's own salesmen (P2): click tests against the real server, 2026-10-16

Flow: `desktop/integration_test/sc_sm_test.dart`. Book: `09_PRICING_AND_INCENTIVES.md`,
TC-SELL-114 to TC-SELL-118, and `10_TERRITORY.md` TC-TERR-007 (the cases that said
"no screen was clicked").
Firm **T10161CKS-R** (Ready t10161cks), built by `scripts/test_fixture.py ready-firm`
(SCHEMA store, every Set up step done, WHOLESALE profile, the whole sales chain
typed, customer FXCUST *Fixture Customer t10161cks*). Users:
`t10161cks.readyadmin@fixtures.local` (Firm admin) and
`t10161cks.readyviewer@fixtures.local` (VIEWER), password `Fixture@2026pw`.
Window 1600x1000.

The fixture holds no product, so the admin run makes one over HTTP the first
time (`SM Product <suffix>`, code `<SUFFIX>-SM`, GST 18 local, PIECE, 50 on hand
at 60 in Main Warehouse), in the shape `test_fixture.py` gives its own products.

## How to run it

From `desktop/` in Git Bash, one run at a time, admin first:

```
IT_EMAIL=<suffix>.readyadmin@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=1200 bash integration_test/run.sh sc_sm_test.dart
IT_EMAIL=<suffix>.readyviewer@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=900 bash integration_test/run.sh sc_sm_test.dart
```

The admin run takes about five minutes after the build. `IT_PART=list`,
`chain` or `required` runs one part (`chain` and `required` read the entries
`list` made earlier in the same run, so run `list,chain` together). Give each
run its own fresh `TEMP`/`TMP` folder: three of six admin runs died with "did
not complete" and `PathNotFoundException ... flutter_tools.*\flutter_test_listener.*`
even in a private folder; the same flow then ran clean in a new folder. Names
carry the minute the run started (`Phone order 0532`), so a second run on the
same fixture does not collide with the first; a run that ties an entry to the
signed-in user first unties any entry an earlier run left tied.

What the flow does, as the Firm admin: Settings > Selling > its one card >
**2 Salesmen** tab, then New / Edit in the list's own form; Sell > Sales Orders
> New and Sell > Sales Invoices > New, reading the **Salesman** box (what it
holds, and every name it offers) before saving; Settings > Selling > **1 Sales
stages** > window for the *Salesman required* switch. Every save is read back
over HTTP. The order is approved, delivered and dispatched over HTTP so a note
exists to bill; a second order with no salesman is raised the same way before
the switch goes on. The switch is put back off (and, failing that, over HTTP),
so the fixture is left as found. As the Viewer: the same Salesmen tab and
Sales stages window, a `POST /api/v1/salesmen` over HTTP, and the Sales Orders
toolbar. App errors and overflows are counted the whole time.

## Results

| Case | Step | Firm admin | Viewer | Note |
| --- | --- | --- | --- | --- |
| — | Salesmen opens from Settings > Selling | PASS | not offered | Columns Code, Name, User account, Phone, Commission, Status; *+ New* enabled. The tab needs `SALESMAN_MANAGE`, which the Viewer does not hold, so the Selling subject shows the Viewer no Salesmen tab (by design, see findings) |
| TC-SELL-114 | New: `Phone order`, no user, Earns commission off | PASS | — | "Salesmen saved."; server `user_id` null, `earns_commission` false; row reads *Not tied to a user, Does not earn, Active* |
| TC-SELL-114 | The order offers it, saves it | PASS | — | SO-2026-2027-000005 saved naming *Phone order 0532* |
| TC-SELL-114/115 | The bill off that order's note | PASS (after fix) | — | Box shows *Phone order*, SI-26-27-000003 saved with it. **Failed before the fix**: box read *Nobody* (see findings). Counter bill not driven: this firm bills notes |
| TC-SELL-118 | New `phone order` (other case) refused | PASS | — | Form stays open, nothing saved, "A salesman named phone order 0532 is already on the list." |
| TC-SELL-118 | `Phone Order 2` saves; Edit to `PHONE ORDER` refused | PASS (after fix) | — | Now says "A salesman named PHONE ORDER 0532 is already on the list."; server name unchanged. **Failed before the fix**: said "Somebody else saved this salesman while you were editing it" (see findings) |
| — | Edit: a phone added, kept; Earns commission untouched | PASS | — | |
| TC-SELL-115 | Entry tied to the signed-in user; new order starts on it | PASS | — | Box starts on *Asha* |
| TC-SELL-115 | That entry made inactive: not offered, not the starting choice | PASS | — | Row reads *Inactive*; new order starts on *Nobody*; offers only active entries |
| TC-SELL-116 | Salesman required switched on | PASS | — | "Sales stages saved."; server false -> true |
| TC-SELL-116 | Order with no salesman refused | PASS | — | Editor open, nothing saved, "This firm requires a salesman on every order, delivery note and bill. Choose one in the Salesman box." |
| TC-SELL-116 | Bill with no salesman refused | PASS | — | Same words, nothing saved |
| TC-SELL-116 | Switch back off; the order and the bill then save | PASS | — | SO-2026-2027-000007 and SI-26-27-000004 saved with no salesman; server false |
| — | Viewer: Salesmen list cannot be changed | — | PASS | Tab not offered; `POST /api/v1/salesmen` answers 403; count 12 -> 12 |
| — | Viewer: Salesman required cannot be changed | — | PASS | Switch shown off and disabled, Save disabled; server false -> false |
| — | Viewer: Sales Orders has no New | — | PASS | |

Last full runs: Firm admin passed 16, failed 0, not run 4; Viewer passed 3,
failed 0, not run 0. No app error and no overflow in either. Before the two
fixes the admin run had passed 15 and failed 1 (the bill box), and the
TC-SELL-118 edit passed only because the flow did not yet read the words.

Not driven:

- **TC-SELL-115** account-manager and round starting choices (QA-C01 / QA-C02):
  the ready fixture has no round and none of the case's customers.
- **TC-SELL-116** delivery note and quotation: only the order and the bill
  were driven.
- **TC-SELL-117** Order By on the print: the printed bill is a PDF preview, and
  its text is not reachable from a click flow.
- **TC-TERR-007**: the ready fixture has no territory, route or round to
  assign a salesman to.

## Findings

- **A name clash on Edit was reported as somebody else's save** (fixed).
  TC-SELL-118 as readyadmin: Settings > Selling > Salesmen, select
  `Phone Order 2 0505` > Edit > Name `PHONE ORDER 0505` > Save & Close. The
  form said "Somebody else saved this salesman while you were editing it. Your
  changes are still here and have not been sent. Copy anything you need, then
  close and reopen to see theirs." The server had answered 409 "A salesman
  named PHONE ORDER 0505 is already on the list." The generic list form
  (`desktop/lib/ui/resource_management_page.dart`, the update branch) rewrote
  *every* 409 on a resource that sends its version as a lost race; the delete
  branch beside it already used `isStaleWrite`. It now does the same, so only
  the server's stale-write sentence is rewritten and any other 409 is shown as
  sent. This applies to every list screen whose definition has
  `updateRecord`. Guarded by two cases in `desktop/test/salesmen_page_test.dart`
  (a clash says so; a lost race still says somebody else saved).
- **A bill's Salesman box ignored the note ticked from the list** (fixed).
  TC-SELL-114/115 as readyadmin, with two notes waiting for the customer:
  Sell > Sales Invoices > New > customer > the tick list opens > tick the note
  of an order naming *Phone order* > Done. The Salesman box read *Nobody*
  (the customer's starting choice) although the note names *Phone order*; the
  bill saved anyway carried *Phone order* (the server takes the note's), so
  the screen showed one thing and saved another, and a person who then chose
  somebody by hand would have overridden the note without knowing it.
  `_setDocuments` in `desktop/lib/ui/sales/sales_invoice_editor_dialog.dart`
  (the tick list and the one-note-waiting path) did not refill the box, where
  choosing a note one at a time did. It now schedules the same fill when the
  primary note changes. Guarded by "phase 2 bill: a note ticked from the list
  brings its salesman" in `desktop/test/sales_invoice_editor_test.dart`
  (fails without the fix).
- **The Viewer cannot see the salesman list at all** (observation, not
  changed). Reading the list needs only membership on the server, but the
  Salesmen tab is gated on `SALESMAN_MANAGE`
  (`desktop/lib/ui/workspace/module_catalog.dart`, the `salesmen` tab), so a
  read-only role is offered no read-only view. The catalogue comment says this
  is deliberate; the brief's "the list opens read-only" does not happen.
- **Fixture residue**: the runs on T10161CKS-R left 12 entries (one `Asha`
  still active from a run cut off mid-way; `Asha 0532` inactive and tied to readyadmin), seven orders, five notes, four bills in draft
  and one dispatched note unbilled (DN-26-27-000001). Salesman required is off,
  as found.
