# Manual UI test plan

Scripted manual tests for the Flutter desktop client against a real backend.
Written to exercise the things automated tests cannot: a human switching firms,
two machines pointing at one server, and the behaviour a low-specification
Windows box actually gives you.

Every case is written from the code as it stands on 2026-08-16. Where a case
covers something **not yet built** it says so and is not executable — those are
drafted so the feature arrives with its tests rather than after them.

A case that needs a request the desktop cannot make is marked **(HTTP)** and
gives the `curl`. Those are still manual tests — they check a guarantee the
server owes, and marking them keeps the plan honest about what clicking can and
cannot prove.

---

## 1. Before you start

### 1.1 What the test environment already gives you

The seeded environment covers all three storage modes, which is the hard part
of this application. Do not rebuild it unless a case says to.

| Firm | Storage mode | Where its data lives |
| --- | --- | --- |
| `WHOLE01` | `SCHEMA` | schema `wholesale_hub` in `agency_platform` |
| `FOOD01` | `SHARED` | schema `firm_shared` in `agency_platform` |
| `MEDI01` | `SHARED` | schema `firm_shared` in `agency_platform` |
| `ELEC01` | `DATABASE` | schema `electrolink_ops` in a **separate database**, `agency_electrolink` |

`FOOD01` and `MEDI01` sharing one schema is the important pair: their rows sit
in the same physical tables, separated only by `firm_id`. Most isolation
defects show up there first.

### 1.2 Accounts

| Login | Password | Firms | Use it for |
| --- | --- | --- | --- |
| `master.ops@agency.local` | `DemoAdmin@12345` | all 4 | firm switching, cross-firm isolation |
| `whole01.admin@agency.local` | `DemoAdmin@12345` | WHOLE01 only | single-firm behaviour, SCHEMA mode |
| `food01.admin@agency.local` | `DemoAdmin@12345` | FOOD01 only | SHARED mode |
| `medi01.admin@agency.local` | `DemoAdmin@12345` | MEDI01 only | SHARED mode, the other half of the pair |
| `elec01.admin@agency.local` | `DemoAdmin@12345` | ELEC01 only | DATABASE mode |
| `platform-admin@agency.local` | see `AGENCY_BOOTSTRAP_ADMIN_PASSWORD` in `backend/config/.env` | **none** | platform administration, and the "admin is not exempt" cases |

The four firm admins hold `FIRM_ADMIN`. To test permission behaviour you will
need users with narrower roles — see §7.1.

### 1.3 Recording a result

For each case record: **date, tester, build, firm under test, PASS/FAIL, and
for a failure the exact on-screen message plus the `requestId` from the error**.
Every API error response carries a `requestId`; quoting it lets a developer find
the exact request in the server log. A failure report without it usually costs a
round trip.

---

## 2. Installation and first run

> **The installer is `install\install.bat` (or `install\install.ps1`).**
> Run `install.bat -DryRun` first: it reports every step and changes nothing.
>
> 2.2 and 2.5 were verified on a developer machine on 2026-08-14. **2.1, 2.3 and
> 2.4 can only be answered on a machine that has never had the toolchain**, and
> that has not been done — a developer box passes 2.1 because of what is already
> on it.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 2.1 | Clean install on a machine with nothing installed | Run `install.bat -InstallPrerequisites -WithDemoData` on a Windows box with no Python, no PostgreSQL, no Flutter | Everything needed is fetched and installed; the UI opens at the login screen without any further prompt |
| 2.1b | Clean install, prerequisites refused | Run `install.bat` (no `-InstallPrerequisites`) on the same box | Stops before changing anything, naming what is missing and the exact `winget install` command for it |
| 2.2 | Re-run on an already-installed machine | Run the installer a second time | It detects what is present, does not reinstall or duplicate, and still ends at a working UI. **`config\.env` must be untouched** — check the JWT key is the same |
| 2.3 | Install with no internet | Disconnect, run the installer | It fails with one clear message naming what it could not fetch — not a stack trace, and not a half-installed state |
| 2.3b | Half a TLS configuration | Run with `-CertFile` and no `-KeyFile` | Refused before anything is changed. It must not fall back to plain HTTP |
| 2.4 | Install on the minimum supported machine | Use the lowest specification you intend to support | Install completes; note wall-clock time and peak RAM. Record them: they are the number that decides whether the requirement is met |
| 2.5 | Manual install per `CLAUDE.md` | Follow the backend and desktop commands | Backend serves `/health`; `flutter run -d windows` opens the login screen |

**When the installer is built, it must be tested on a machine that has never had
the developer toolchain on it.** An installer tested only on a developer's
machine passes because of what is already there.

---

## 3. Connecting the UI to the backend

This section carries the requirement that the UI runs on a different machine
from the backend. **Read 3.3 before planning that deployment.**

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 3.1 | Same machine, default | Launch the client with the backend on the same box | Connects; login screen loads |
| 3.2 | Change the server address in the UI | Open application settings, set the server URL, save | Accepted, persisted, and used after restart |
| 3.3 | **Remote backend over plain HTTP on the LAN** | Start the backend with `-BindHost 0.0.0.0`, set the URL to `http://<server-lan-ip>:8000` | **Accepted.** This is the supported LAN deployment — see the note below for what it costs |
| 3.3b | Plain HTTP to a public address | Set the URL to `http://erp.example.com` | **Refused**, and the message says passwords would cross in clear text |
| 3.4 | Remote backend over HTTPS | Set the URL to `https://<server-host>` with a certificate the client trusts | Connects and works exactly as local |
| 3.5 | Remote backend, untrusted certificate | Point at an HTTPS server with a self-signed certificate the machine does not trust | Fails with a certificate error, not a blank screen or a hang |
| 3.6 | Server unreachable | Point at a host that is down | A clear "cannot reach the server" message; the app stays usable enough to correct the address |
| 3.7 | Server address with credentials or query | Try `https://user:pass@host` or `https://host?x=1` | Refused — the client rejects user-info, query and fragment in the server URL |
| 3.8 | Two UIs, one backend | Run the client on two machines against the same server, log in as different users | Both work; neither sees the other's session |
| 3.9 | Two UIs, same user | Log in as the same user on two machines | Both work. Note what happens when one changes a record the other is viewing — see §9 |

> ### Both transports are supported, and the firm chooses
>
> Decided on 2026-08-14. `normalizeServerUrl` in
> `desktop/lib/core/preferences/desktop_preferences_service.dart` accepts
> `https://` anywhere and `http://` to an address on the client's own network —
> loopback, `10.x`, `172.16-31.x`, `192.168.x`, `169.254.x`, the IPv6 local
> ranges, a hostname with no dots, or a `.local` / `.lan` / `.internal` suffix.
> Plain HTTP to a public address is refused.
>
> **What plain HTTP costs.** On that network the login password and every record
> are readable by anything else on the wire. A firm running its own switch can
> reasonably accept that. On a network it does not control — a shared office
> building, anything with guest wifi — serve TLS instead:
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File scripts\start_backend.ps1 `
>   -BindHost 0.0.0.0 -CertFile C:\certs\erp.crt -KeyFile C:\certs\erp.key -NoReload
> ```
>
> Every client machine has to trust that certificate. A self-signed one means
> installing it in each Windows trust store, which is the installer's job.
> **3.5 is still expected to fail** — an untrusted certificate must produce a
> certificate error, and turning verification off is not the fix.
>
> The boundaries are covered by `desktop/test/server_url_rule_test.dart`, so
> changing what counts as "your own network" changes a test that says why.

---

## 4. Login, session and logout

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 4.1 | Valid login | Log in as `whole01.admin` | Lands on the workspace with the firm shown in the shell |
| 4.2 | Wrong password | Enter a bad password | Rejected with a generic message. It must **not** say whether the email exists |
| 4.3 | Unknown email | Log in with an address that does not exist | Same generic message and comparable response time as 4.2 |
| 4.4 | Bootstrap admin first login | Log in as `platform-admin` | Forced to change the password before anything else |
| 4.5 | Password persistence | Log in, close the app, reopen | Not asked for the password again (the refresh token is in the Windows credential vault); the password itself is never stored |
| 4.6 | Session survives a token expiry | Stay logged in until the access token expires, then act | The client refreshes once automatically and the action succeeds — no visible interruption |
| 4.7 | Refresh token revoked | Log out on machine A, then act on machine B with the same account | B is returned to the login screen cleanly, not left in a broken half-session |
| 4.8 | Logout clears the vault | Log out, reopen the app | Login required |
| 4.9 | Backend restarted mid-session | Restart the backend while logged in, then act | The action either succeeds or fails with a clear message; the client does not need reinstalling |

---

## 5. Multi-firm access — the core of this plan

### 5.1 Firm switching

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 5.1.1 | Switch between all four firms | As `master.ops`, use **Switch firm** to visit WHOLE01 → FOOD01 → MEDI01 → ELEC01 | Each switch succeeds; the shell header shows the firm you switched to |
| 5.1.2 | Data changes with the firm | Note the customer list in WHOLE01, switch to FOOD01, look again | A completely different list. No row from one firm appears under the other |
| 5.1.3 | Switching survives a restart | Switch to ELEC01, close the app, reopen | Either the same firm is still active, or you are asked to choose — **never** silently active in a different firm |
| 5.1.4 | Single-firm user has no switcher | Log in as `food01.admin` | Either no firm switcher, or one offering only FOOD01 |
| 5.1.5 | Switch with unsaved work | Start editing a document, switch firm without saving | You are warned, or the edit is discarded cleanly. The edit must **not** be saved into the firm you switched to |
| 5.1.6 | Rapid switching | Switch firm several times quickly | No stale data. Every list matches the firm currently shown |

### 5.2 Isolation between firms sharing one schema (FOOD01 / MEDI01)

**This pair matters most.** Both live in `firm_shared`; their rows are in the
same tables and only `firm_id` separates them.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 5.2.1 | Create in one, absent in the other | Create customer `ISO-TEST-1` in FOOD01. Switch to MEDI01, search for it | Not found |
| 5.2.2 | Same code in both firms | Create a customer with code `DUP-01` in FOOD01, then the same code in MEDI01 | Both succeed. Codes are unique per firm, not globally |
| 5.2.3 | Direct access by id | Note a FOOD01 customer's id from its URL or detail screen; switch to MEDI01 and try to open that id | Not found — not "access denied" leaking that it exists, and certainly not the record |
| 5.2.4 | Search does not cross firms | Search a term that matches records in both | Only the active firm's rows |
| 5.2.5 | Reports do not cross firms | Open any summary or report in FOOD01, compare with MEDI01 | Totals differ and correspond to each firm's own data |
| 5.2.7 | **Global search works at all from inside a firm** | Sign in as any firm admin, pick a firm, press **Ctrl+K** and search anything | Results. Until 2026-08-16 every query answered 503 — `users`, `roles`, `permissions` and `firms` live only in the platform schema and were read on the firm's session, and one failing entity aborted the whole search |
| 5.2.8 | Platform records are found from inside a firm | With a firm selected, Ctrl+K and search a user's name, then a role name | Both found, alongside firm-owned records. Reaching the platform store is the fix; quietly dropping those entities would look the same on 5.2.7 alone |
| 5.2.6 | Platform admin sees no merged list | As `platform-admin`, open a firm-owned screen with no firm selected | Refused or empty — **not** every firm's rows in one list. This was a real defect in global search; verify it stays fixed |

### 5.3 Isolation across storage modes

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 5.3.1 | SCHEMA mode works end to end | In WHOLE01 create a customer, a product, and a sales order | All succeed and appear in WHOLE01 only |
| 5.3.2 | DATABASE mode works end to end | Repeat in ELEC01, whose data is in a different database | Identical behaviour. Slower is acceptable; different behaviour is not |
| 5.3.3 | Dedicated firm is invisible to shared | Create `ISO-ELEC-1` in ELEC01, then search every other firm | Not found anywhere |
| 5.3.4 | The separate database really is separate | Ask an admin to stop or block `agency_electrolink` only | ELEC01 shows a clear error; **WHOLE01, FOOD01 and MEDI01 keep working** |
| 5.3.5 | Attachments and documents follow the firm | Create a document with an attachment in each mode | Each is retrievable in its own firm and nowhere else |

### 5.4 User–firm membership combinations

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 5.4.1 | User with no firms | Log in as `platform-admin` | Platform screens work; firm-owned screens ask for a firm or are hidden. No crash |
| 5.4.2 | User with one firm | `food01.admin` | Goes straight to FOOD01 |
| 5.4.3 | User with several firms | `master.ops` | Asked to choose, or defaults to their primary firm — and the shell says which |
| 5.4.4 | Membership removed while logged in | With `master.ops` logged in and active in FOOD01, have an admin deactivate that membership; then act in FOOD01 | Refused with a clear message. The user must not keep working in a firm they were removed from |
| 5.4.5 | Membership added while logged in | Grant a new firm to a logged-in user | It appears in the switcher — after a refresh or re-login is acceptable; document which |
| 5.4.6 | Deactivated user | Deactivate a user who is logged in, then have them act | Refused; returned to login |
| 5.4.7 | Different roles per firm | Give a user `FIRM_ADMIN` in one firm and a read-only role in another; switch between them | Permissions change with the firm. Buttons available in one are absent in the other |

---

## 6. Business profile features

Feature gating went live on 2026-08-10 and **changes what the UI is allowed to
submit**. Testers will meet these refusals and must not file them as bugs
without checking the firm's profile first.

Nine features are enforced: `BATCH_TRACKING`, `SERIAL_NUMBER`,
`EXPIRY_TRACKING`, `MANUFACTURING_DATE`, `SHELF_LIFE`, `WARRANTY`, `BARCODE`,
`QR_CODE`, `DRUG_LICENSE`, `VEHICLE_TRACKING` and `ATTACHMENTS`.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 6.1 | A feature the firm has | In WHOLE01 (profile enables `BARCODE`) save a product with a barcode | Saved |
| 6.2 | A feature the firm lacks | In WHOLE01 (profile does **not** enable `EXPIRY_TRACKING`) create a batch **with** an expiry date | Refused, naming the feature and the field |
| 6.3 | The record without the field | Same firm, create the same batch **without** an expiry date | **Succeeds.** The feature governs the field, not the record. If the whole batch is refused, that is a bug |
| 6.4 | Clearing a gated field | On a record that already has a gated value, clear it and save | Allowed. Turning a feature off must never freeze existing records |
| 6.5 | Document with no attachments | In a firm without `ATTACHMENTS`, save a document attaching nothing | Succeeds. Being refused here is a bug — it was one, and was fixed |
| 6.6 | Existing attachments still readable | In a firm without `ATTACHMENTS`, open a document that already has files | Files listed and downloadable |
| 6.7 | Roadmap features are not switchable | As platform admin, try to enable `RECIPE_MANAGEMENT`, `COMMISSION`, `IMEI`, `PRESCRIPTION_REQUIRED`, `KITCHEN_MANAGEMENT`, `SERVICE_CONTRACTS` or `PROJECT_MANAGEMENT` on a profile | Refused. Nothing implements them |
| 6.8 | **UX gap to assess, not a pass/fail** | Note whether the UI *hides* fields the firm's profile disables, or lets you type and then refuses on save | Record what happens. Today the backend refuses; the desktop does not pre-hide. Decide whether that is acceptable |

---

## 7. Permissions and roles

### 7.1 Setting up

Most cases need users narrower than `FIRM_ADMIN`. As a firm admin, create one
user per role you want to exercise — `SALES_EXECUTIVE`, `ACCOUNTANT`,
`VIEWER`, `CASHIER` are the informative ones.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 7.2 | Read-only user | Log in as a `VIEWER` | Lists load. Create, edit and delete are absent or disabled — **not** present and failing on click |
| 7.3 | Menu matches permission | Compare the module list for `VIEWER` and `FIRM_ADMIN` | The viewer sees fewer modules |
| 7.4 | Hidden is not the same as safe | Note a URL or action a `VIEWER` cannot see; attempt it directly if the UI allows | Refused by the server. Menu filtering is cosmetic and must not be the only guard |
| 7.5 | Credit policy is not editable by sales | As a `SALES_MANAGER`, open the customers workspace, **Settings** | The credit policy is visible but read-only, with a line naming the missing permission |
| 7.6 | Credit policy is editable by an accountant | Repeat as `ACCOUNTANT` | Editable and saveable |
| 7.7 | Platform admin is not exempt from firm scope | As `platform-admin` with no firm selected, open a firm-owned screen | Refused. Platform authority does not bypass firm context |
| 7.8 | Permission change takes effect | Change a logged-in user's role | The change applies after a refresh or re-login; document which |

---

## 8. Business behaviour worth checking by hand

These are drawn from defects that actually occurred. Each is cheap to check and
each was, at some point, wrong.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.1 | Interstate tax is IGST | Raise a sales invoice where the customer's state differs from the branch's | A single IGST line, **not** CGST + SGST. Two lines here is a filing error |
| 8.2 | Local tax is CGST + SGST | Same, with the customer in the same state | Two lines |
| 8.3 | Tax-inclusive pricing | Use a tax profile marked inclusive | The tax is shown but **not added on top** of the price |
| 8.4 | Stock ledger opens | Open the stock ledger for a product that has moved | It loads. This screen used to error for any firm that had ever moved stock |
| 8.5 | Expiry dashboard agrees with itself | In a firm with expiry tracking, compare the expired **count** with the expired **list** | They match |
| 8.6 | Delivery-by-route report | Open the delivery note report grouped by route, with a route set on a note | It loads and names the route. It used to crash |
| 8.7 | Tax rules filtered by transaction type | Open tax rules, filter by transaction type | Results returned. This was a 500 until 2026-08-10 |
| 8.8 | Credit limit warns | Approve a sales order taking a customer past 80% of their credit limit | A warning appears **and the order is still approved** |
| 8.9 | Credit limit blocks only if configured | Set the firm's credit policy to Block, then exceed the limit | Now refused, naming the customer and the percentage |
| 8.10 | Import is all or nothing | Import a branch file where one row duplicates an earlier row's code | Refused, **nothing** imported, and the message says so. Then fix the file and re-import: it must succeed |
| 8.11 | Document totals | Create a document with discounts, charges and round-off | Header totals equal the sum of the lines. Check to the last paisa |
| 8.12 | Editing a document keeps its links | Edit an approved-then-reopened document's lines and save | Downstream documents still reference the right lines |
| 8.13 | Audit trail is per firm | Make a change in FOOD01, then open the audit log in MEDI01 | The FOOD01 change is **not** there. Each firm has its own trail |
| 8.14 | Receive goods against an order | Goods Receipts → **New Receipt**, choose an approved order, accept the quantities, save | A draft GRN. Stock has **not** moved yet — completing it is what posts stock |
| 8.15 | A part-received order defaults to what is left | Complete a receipt for part of an order, then raise a second receipt against the same order | The second receipt defaults to the outstanding quantity, not the full order. Saving the full order again is refused for over-receipt |
| 8.16 | The batch on the carton reaches the shelf | Receive a line with a batch number, then complete it | A batch of that number exists under Batches, holding what was received. The stock row is that batch's, not the product's |
| 8.17 | A batch-tracked product refuses a blank batch | Receive a product whose profile requires a batch on receipt, leaving the batch number empty | Refused **before** the round trip, naming the line. Completing it server-side is refused too |
| 8.18 | Deliver against an order | Delivery Notes → **New Note**, choose an approved order, save | A draft note. Stock has **not** moved — dispatching it is what moves it |
| 8.19 | A line defaults to what is reserved | Compare the Delivering box with the line's ordered and reserved figures | It matches **reserved**, not ordered. Delivering more than is reserved is refused at dispatch |
| 8.20 | The batch preview matches what ships | Note which batches a line says it will ship from, then dispatch it and open the stock ledger | The dispatch came off those batches, earliest expiry first |
| 8.21 | An unapproved order cannot ship | Open a note for an order with nothing reserved | The line says so and Save is refused. It must not offer to ship stock nobody committed |
| 8.22 | Return goods to a supplier | Purchase Returns → **New Return**, choose a completed receipt, save | A draft return. Approving **and** completing it is what takes the stock off |
| 8.23 | The batch is chosen, not typed | Open a return line for a batch-tracked product | A dropdown of that product's registered batches showing what each holds, defaulting to the batch the receipt brought in. There must be **no** free-text batch box |
| 8.24 | The return comes off the named batch | Complete a return for a batch, then open Batches | That batch holds less by exactly the returned quantity. The stock ledger names it on the RETURN row |
| 8.25 | The whole loop balances | Receive 20 on a batch, deliver 5, return 5 | The batch holds 10, and the ledger shows GOODS_RECEIPT +20, DISPATCH −5, RETURN −5 all naming it |
| 8.26 | Approving an order holds a batch | Approve a sales order for a batch-tracked product, then open the stock ledger | A RESERVE naming the batch nearest expiry. It must **not** land on a row holding nothing |
| 8.27 | Nothing goes negative from a reservation | After 8.26, check the product's stock rows | No row has a negative available quantity. That was the symptom of reserving the product instead of the batch |
| 8.28 | Opening stock can name its batch | Post an opening stock document with a batch number on a line | The batch appears under Batches holding that quantity, and the stock row is that batch's |
| 8.29 | Day-one stock obeys the receipt rule | Post opening stock for a product that requires a batch on receipt, leaving the number blank | Refused, naming the product. The rule is not only for goods receipts |

### 8.30–8.34 Importing sales returns and quotations

**These are API cases.** Both modules import over HTTP and neither workspace has
an import button, so drive them with `curl` — see `.claude/skills/run-app` for
the token. They are here rather than left to the unit suite because 8.10 is the
case this project has been bitten by twice, and these are the two newest imports.

The batch is `POST /api/v1/{sales-returns,quotations}/import` with
`format=json` and `payload={"records":[...]}` as form fields, up to 500 records.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.30 | A quotation batch lands whole | Import two valid quotations in one call | 201 with both, each carrying **its own** document number. The list count rises by exactly two |
| 8.31 | A refused batch leaves nothing | Import two quotations giving both the **same** explicit `quotation_number` | **409**, and the quotation count is **unchanged**. Not 500: a duplicate number is a conflict the caller can fix, and half a file must never land |
| 8.32 | The corrected file then works | Fix 8.31's file to use distinct numbers and re-import | 201. This is the half of 8.10 that actually matters — a partial import makes the corrected file fail on its own earlier rows |
| 8.33 | A sales return batch is refused whole | Import two returns against one delivery note where the second returns far more than was dispatched | **422** naming the quantity, and the sales-return count is **unchanged** |
| 8.34 | A return batch sees its own earlier rows | Import two returns of 1 unit each against the same delivery note line | Both accepted. The second must count the first's claim — they are staged on one transaction, so an over-return split across a batch is still caught |

### 8.35–8.37 Exporting

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.35 | Sales return export | `GET /api/v1/sales-returns/export` | CSV: a header row plus one row per return, carrying the number, dates, customer, branch, warehouse, status, returned quantity and total |
| 8.36 | Quotation export names what lapsed | `GET /api/v1/quotations/export` with one live and one expired quotation, **both still `DRAFT`** | An `is_expired` column reading `false` and `true`. The `status` column reads `DRAFT` for both — which is the point: expiry is derived from `valid_until`, so status alone cannot answer it |
| 8.37 | Export respects the firm | Export quotations as `food01.admin`, then as `medi01.admin` | Each sees only its own. These two share one schema, so this is the isolation case that matters |

### 8.40–8.46 Quotations

The module shipped without manual cases. These are the ones worth a human,
because most of them are about what a quotation **does not** do and about lines
quietly disappearing — neither shows up as an error message.

Sales → Quotations, as `whole01.admin`.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.40 | A quotation commits nothing | Create and send a quotation for a stocked product, then open the stock ledger and the customer's account | **No** reservation, no movement, no change to what the customer owes, no journal. Everything the firm promises happens at conversion, on the order |
| 8.41 | More than one line | **New Quotation**, fill the first line, press **Add line**, fill the second, save | Both lines are on the saved quotation, numbered 1 and 2. The form wrote a single line until 2026-08-15 — a quotation for two products could not be raised from the desktop at all |
| 8.42 | Each line shows its own total | With two lines of different value, read the per-line figures and the offer total | Each line shows what it contributes; the total is their sum. One total alone does not say which line was mistyped |
| 8.43 | Removing a line takes its own numbers | Enter three lines with distinct quantities, remove the **middle** one, save | The saved quotation holds the first and third lines **with their own quantities and prices**, renumbered 1 and 2. If the third row inherits the second's numbers, the editor is keeping its fields in lists indexed by position |
| 8.44 | The only line cannot be removed | On a quotation with one line, look at that line's remove control | Disabled, and its tooltip says a quotation needs at least one line. It must not let the save fail instead |
| 8.45 | Revising keeps the whole offer | Create a two-line quotation, reopen it with **Revise**, change nothing, save | **Both** lines survive. This is the case to run twice: the update replaces the whole line collection with what is sent, so seeding only the first line is a silent deletion — no error, no warning, one line simply gone |
| 8.46 | A discount comes back as it was quoted | Put 10% on a line, save, then reopen with **Revise** | The field reads 10, not 0. Only the resulting **amount** was parsed before, so a revision re-sent the line at full price |

Expiry is derived from `valid_until` rather than stored, so 8.45 and 8.46 need a
quotation that has **not** lapsed — an expired one cannot be sent, accepted or
converted, and the workspace badges `EXPIRED` separately from the status because
`SENT` reads identically the day before and the day after.

### 8.80–8.84 A purchase order is submitted, then approved

Built on 2026-08-16, after testing found the Open Orders tab permanently
empty. Until then `cancel` and `close` were the only real transitions on a
purchase order — every other status came from whatever the creator typed on
the form, so `SUBMITTED` could not be produced by anything a user did.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.80 | A draft can be submitted | Purchases → **New**, save a draft, select it | A **Submit** button appears. Pressing it moves the order to SUBMITTED |
| 8.81 | Approval needs a submission first | On a **draft**, look for Approve | There is none. Over HTTP, `POST /purchases/{id}/approve` on a draft is refused with "Submit the order first" — an approval anyone can skip is not a control point |
| 8.82 | A submitted order can be approved | Select the submitted order | An **Approve** button appears; pressing it moves the order to APPROVED |
| 8.83 | Approving needs the approve right | Sign in as a user with `PURCHASE_UPDATE` but not `PURCHASE_APPROVE` | Submit is offered, Approve is not. The person who raises an order need not be the one who commits the firm to it |
| 8.84 | The Open Orders tab finally has something | After 8.80, open **Open Orders** | The submitted order is listed. That tab filters on SUBMITTED and was empty for every firm before this |

Each step writes a history row, a lifecycle event and an audit entry — check
the order's history shows `DRAFT->SUBMITTED` and `SUBMITTED->APPROVED`.

### 8.70–8.72 A branch or warehouse can say what type it is

Raised from testing on 2026-08-16: the New Branch form had no type field, so
the Branch Types and Warehouse Types screens were lists you could curate and
never apply. Every branch and warehouse in the demo carried no type.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.70 | The field is there and offers the firm's types | Masters → Branches → **New**, look at the form | A **Branch Type** dropdown listing the types defined under Branch Types, plus **None**. Same on the warehouse form |
| 8.71 | The choice is saved | Pick a type, save, reopen the record | The type is still selected. Set it back to **None**, save, reopen — it is cleared, not left on the old value |
| 8.72 | A firm with no types can still save | Delete or ignore all types, then create a branch | The dropdown says "None defined — add one under Branch Types" and the branch saves. A type is optional; being unable to classify must never block creating a branch |

### 8.73–8.79 A branch or warehouse can say where it is — and keeps it

Built on 2026-08-16. `branches` and `warehouses` carry six geography keys and
two street lines and **no free-text city at all**, so the masters are the only
way to record a place — and no screen ever set one. Worse, the update dumped
its whole write model and assigned every field, while the form hardcoded
`is_default: false`, `gst_registration: false` and all ten warehouse capability
flags. **One rename cleared the address, the city, the default flag and the GST
registration.**

8.75 is the case that matters. Run it on a record you have just given an
address to, not on a blank one, or it passes for the wrong reason.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.73 | The address form is there | Masters → Branches → edit a branch | An **Address** section: two street lines and a Country → State → District → City → Pin code → Locality ladder. Same on the warehouse form |
| 8.74 | The place is saved and comes back | Fill the ladder down to a pin code, save, reopen | Every rung is still chosen. Each rung stays disabled until its parent is picked, and changing the City clears Pin code and Locality — anything below a changed rung stops meaning anything |
| 8.75 | **A rename keeps the address** | Give a branch an address, tick **Default branch** and **GST registered**, save. Now change only its **name** and save again. Reopen | Address, place, Default and GST are all exactly as they were. Until this was fixed the rename cleared every one of them |
| 8.76 | The warehouse keeps its capabilities | Tick **Cold storage**, **Hazardous storage** and **Loading dock** on a warehouse, save, then rename it and reopen | All three still ticked. Ten flags were reset by every save |
| 8.77 | A new warehouse starts sensibly | Masters → Warehouses → **New** | **Receiving area** and **Dispatch area** are ticked, nothing else. Those two were the only honest part of the old hardcoding |
| 8.78 | Clearing really clears | Empty **Address line 2** on a record that has one, save, reopen | Line 2 is empty and **line 1 is untouched**. Absent means leave alone; sending a field empty means clear it, and the two must stay different |
| 8.79 | The taller dialogs still fit | Run at 1366×768 and open both forms | They scroll internally. No clipped content, no overflow stripe. The address ladder made both taller than the screen leaves room for |

### 8.90–8.94 A vendor save keeps what it cannot show

Built on 2026-08-16. The vendor dialog sent all six child collections as empty
lists and the API replaces rather than merges, so correcting a phone number
destroyed the vendor's addresses, contacts, bank accounts, tax details,
attachments and notes. One seeded vendor had already lost its address that way.

**Run 8.90 on a vendor that has contacts and bank details**, not a fresh one.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.90 | **An edit keeps the other tabs** | Open a vendor with contacts and banking, change its **name** only, save, reopen and look at every tab | Contacts, Banking, Tax, Attachments and Notes all still there. This is the defect |
| 8.91 | A vendor address can name its city | Vendors → edit → **Addresses** → add or edit an address, choose a place from the ladder, save, reopen | The place comes back. `vendor_addresses` has no text city column at all, so this is the only way to say where a vendor is |
| 8.92 | Primary is exclusive | Add a second address and tick **Primary** on it | The first one unticks itself. The form applies the rule rather than letting the save be refused for it |
| 8.93 | An existing address keeps its identity | Edit an existing address's street line and save | It is the same row updated, not a new one — check the address count did not grow |
| 8.94 | A firm with no Places can still save | Use a firm whose geography masters are empty | The dropdowns are empty with a hint pointing at Sales → Places, **and the vendor still saves**. Reference data nobody has filled in must not block a write |

### 8.100–8.109 Territory, routes and beat plans

Built across 2026-08-15/16 (PR #86) and never given manual cases until now. See
`docs/TERRITORY_FRAMEWORK.md` for what the pieces mean. Run these on `WHOLE01`,
whose seeded layout is `WHOLE01C02→S1`, `WHOLE01C03→N1`, `OB-REV2→N1`,
`WHOLE01C01→N2`.

**Restore anything you change.** These screens replace whole lists rather than
merging, so a test left half-finished looks exactly like a defect next time.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.100 | A round can be defined | Sales → Territories → **New**, give it a route type and a parent | It is created and appears under its parent. A node becomes a *route* by carrying a route type |
| 8.101 | Shops go on the round in an order | Open a route, assign customers, drag one stop above another, save, reopen | The order held. Dragging used to answer 409: the stop-number key is checked per statement, so a swap collided until the numbers being moved are released first |
| 8.102 | **A failed read cannot overwrite the round** | Open a route with shops, then trigger a read failure (stop the backend, click another route, restart) | The pane is **empty**, not showing the previous route's shops, and Save is refused until it has provably read the route on screen. `PUT /{id}/customers` replaces the whole list, so the pane *is* the record |
| 8.103 | A shop's stop number survives a save that says nothing about order | Re-save a route without touching the order | The sequence is unchanged. Only rows actually moving are renumbered |
| 8.104 | The working days decide the call | Give a route working days of Mon only, point a Tuesday beat plan at it, open the call list for that Tuesday | It does **not** occur, and it says why. Working days were recorded and read only to display themselves back |
| 8.105 | The effective window is judged on the document's date | Set a route's Runs until to yesterday, then tag a document dated today with it | Refused. Back-date the document inside the window and it is accepted |
| 8.106 | A call list for a date | Sales → Territories → **Call list**, pick a date | The shops the plan calls that day, in stop order, naming the route and the salesperson |
| 8.107 | Assign by area | Route Builder → search by pin code or street, select shops, assign to a route, order them | The selection assigns and the order sticks. This is the screen for building a round from geography rather than from a list |
| 8.108 | The hierarchy settings are enforced | Turn on each of the four settings (multi-route per salesman, multi-salesman per route, leaf-only customers, max nodes per parent) and breach each in turn | Each refusal names the rule it broke. All four were stored and checked nowhere |
| 8.109 | A customer shows the rounds that call them | Open a customer who is on two routes | Both routes listed with this customer's stop number on each. Exactly one is primary — see §12 |

### 8.123–126 Cancelling a receipt puts the ledger back too

Added 2026-08-18. Until then cancelling a completed goods receipt took the
stock back off and left the journal posted, so the general ledger's inventory
balance drifted above the warehouse by the value of every cancelled receipt.
Nothing in the desktop showed it; it was found by driving the API and reading
the journals.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.123 | Stock and ledger move together | Receive an order in full, complete the receipt, note the stock figure and the journal | `Dr Inventory / Cr Goods Received Not Invoiced`, at cost and excluding tax |
| 8.124 | **Cancelling reverses both** | Cancel that receipt | Stock returns to what it was **and** a second journal appears — the original reads REVERSED, the mirror POSTED, and every account nets to zero across the pair |
| 8.125 | Cancelling twice changes nothing further | Cancel the same receipt again | Still exactly two journal entries. The mirror carries the same source ids as the original, so a careless lookup would reverse the reversal |
| 8.126 | **An invoiced receipt is refused** | Receive, complete, raise and approve a purchase invoice against it, then cancel the receipt | 422 naming the invoice. Stock unchanged, still one journal. Cancel the invoice first, or raise a purchase return — a return credits the supplier, which cancelling the receipt never could |

### 8.117–122 An edit cannot rewrite an order's status

Added 2026-08-18, after driving the API and finding three ways the approval
step could be bypassed. All three were invisible from the desktop, so these
cases are worth running against the API as well as the screen.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.117 | **Editing an approved order withdraws approval** | Approve an order, then Edit it | A warning first: *"Editing withdraws the approval."* Accept it, change the quantity, save | The order reads **DRAFT** and its History shows `approval_withdrawn`. It must be submitted and approved again |
| 8.118 | Backing out of that warning changes nothing | Same, but choose Cancel | The editor does not open and the order is still APPROVED |
| 8.119 | A received order cannot be edited | Receive part of an order, then select it | **Edit is disabled.** Through the API the same edit answers 422 naming the receipts |
| 8.120 | Cancelled and closed orders cannot be edited | Select one of each | Edit is disabled for both |
| 8.121 | **Goods cannot be received against an unapproved order** | Via the API, POST a goods receipt against a DRAFT order | 422 — *"goods can only be received against an approved order."* Before this it was accepted, and completing it posted stock and posted to the ledger |
| 8.122 | A submitted order keeps its status when edited | Submit an order, edit it, save | Still **SUBMITTED**. Only approval is withdrawn by an edit; nothing else moves |

### 8.110–116 Submit and Approve from inside the open order

Added 2026-08-18. The action used to be reachable only from the workspace
toolbar, against the selected row, so approving meant closing the document you
were reading. Both routes now exist and must stay in agreement.

Run as `whole01.admin@agency.local`, which holds every purchase permission, and
once more as a user with `PURCHASE_VIEW` only.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.110 | The buttons are in the open document | Purchases → Purchase Orders → double-click a **draft** | The dialog toolbar shows **Submit** enabled and **Approve** greyed, beside Save. The panel under the header reads *"Submit this draft to send it for approval."* |
| 8.111 | **Acting does not close the document** | Click **Submit** | The dialog stays open. The status becomes SUBMITTED, Submit greys, Approve lights up, the message changes to *"Approve this order to commit the firm to it."*, and the **History** tab has gained an entry |
| 8.112 | And again for approval | Click **Approve** | APPROVED, both greyed, *"No approval step is outstanding."*, History gains a second entry |
| 8.113 | The grid behind is not left stale — and is not lied to | Close the dialog | The row reads APPROVED and is still selected. There is **no** "Purchase order updated." message: nothing was edited. Editing and saving normally must still show it |
| 8.114 | Permission hides, status disables | Sign in with `PURCHASE_VIEW` only and open any order | Neither button is present at all — not greyed. A submitted order reads *"Waiting for someone who holds purchase approval."* |
| 8.115 | A new order offers neither | Purchases → **New** | No Submit, no Approve, and *"Save the order before it can be sent for approval."* There is nothing on the server to act on yet |
| 8.116 | Both routes still work, and agree | Approve one order from the grid toolbar and another from inside the dialog | Both reach APPROVED. Approving an order somebody else already approved shows the server's refusal in the dialog's **banner**, and the dialog stays usable |

### 8.60–8.63 Sub-tabs load their own data

Reported from testing on 2026-08-15 and fixed the same day. Every module whose
sub-tabs are served by one page class was affected — clicking a sub-tab kept
the previous tab's `State`, so nothing was fetched and the grid showed "no
records" until Refresh. Worth re-running after any change to those pages.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.60 | Every UOM sub-tab loads on the first click | Administration → UOM & Packaging → click **Units**, **UOM Groups**, **Packaging Types**, **Conversion Rules**, **Industry Templates** in turn | Each shows its own rows on arrival. **No Refresh.** This is the case that was reported |
| 8.61 | A search does not follow you | Type a term in the search box on Units, then switch to Packaging Types | The box is empty and the grid unfiltered. On Tax the same case matters more: the search there is sent to the server, so a stale term silently filters the next tab |
| 8.62 | A selection does not follow you | Purchases → tick some rows on **Draft Orders**, then switch to **Open Orders** | Nothing is selected, and the bulk-action bar is gone. A selection that survived could put a bulk close or cancel through against orders that are no longer on screen |
| 8.63 | The two type lists are not each other | Masters → Branches → **Warehouse Types**, then **Branch Types** | Each shows its own list. They share one field internally, so this pair showed the wrong list rather than an empty one |

### 8.55–8.59 A customer address names a real place

Built on 2026-08-16. `customer_addresses` held city, area, district, state and
postal code as plain strings with no link to the geography masters, so "Parrys"
and "Parry's Corner" never grouped and the Route Builder's pin-code search was a
string match. Vendors, branches and warehouses had the keys and no form;
customers had the text and no keys, which is why they needed a migration
(`20260816_0094`).

**The keys are the truth and the free text is derived from them.** That is what
8.56 checks, and it is the case most likely to look like a bug if you have not
read this: choosing a place *overwrites* what you typed.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.55 | The ladder is on the address | Customers → edit → **Address** | Below the existing fields, a **Place** section: Country → State → District → City → Pin code → Locality, each rung loading only after its parent is chosen |
| 8.56 | **Choosing a place rewrites the text** | Type nonsense in City, then choose a real City from the ladder | The City field changes to the master's name. The server derives these columns from the keys, so a form still showing your typing would be showing something it is not about to save |
| 8.57 | The place survives a save | Choose down to a pin code, save, reopen | Every rung is still chosen, and the text matches it |
| 8.58 | An address with no place still saves | Leave the whole ladder on **None** and save | Accepted, with the text exactly as typed. Every client written before these columns did this, and a firm with no Places must still be able to record an address |
| 8.59 | Existing addresses were matched, not invented | Open a seeded customer in `WHOLE01`, then one in `FOOD01` | WHOLE01's are filled down to the pin code; FOOD01's name only a country. That is correct — FOOD01's only state master is "Andera Pradesh" while its addresses are in Telangana, and the migration fills nothing it is not sure of |

**(HTTP)** The refusal that has no screen: send an address whose rungs do not
belong together — a district id under a different state — and the save is
refused naming the level. The picker cannot produce that combination, but
another client can.

### 8.50–8.54 Editing a customer who has traded

**Run these on a seeded firm, not a fresh one.** They are about a customer with
history behind them, and on a customer created five minutes ago every one of
them passes for the wrong reason. `WHOLE01` after a demo seed is the right
subject: pick the customer with the largest outstanding.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 8.50 | An edit keeps what the customer owes | Note the customer's outstanding, edit an unrelated field — a phone number will do — and save. Re-open them | The outstanding is **exactly** what it was. Until 2026-08-15 it was reset to the opening balance, so every invoice, receipt and credit note since was discarded by an edit nobody thought was financial |
| 8.51 | The books agree afterwards | Run `scripts/verify_sample_data.py` after 8.50 | Every store holds together. If it reports "customers owe X against receivable account Y ... a balance moved without a journal", 8.50 has regressed — that is the exact wording this defect produced |
| 8.52 | The edit is not refused | Save the same customer twice in a row | Both succeed. It answered 409 "This record changed since you loaded it" for any customer whose opening balance had posted, with nobody else touching the record |
| 8.53 | An opening balance still cannot be rewritten after trading | Edit the customer and change the **opening balance** | Refused, saying it cannot change after receivable activity exists. That guard is what makes 8.50 safe: the balances are only ever recomputed where there is nothing else to lose |
| 8.54 | A new customer's opening balance still reaches the ledger | Create a customer with an opening balance of 25,000, then open the trial balance | Trade Receivables and Opening Balance Equity have each moved by 25,000. Delete the customer and both move back |

---

## 9. Concurrency and two-machine cases

**Read this before running 9.1.** The precondition that makes a concurrent edit
refusable is `If-Match`, and it is **opt-in**: a request that omits it is
accepted, so existing clients keep working. The server publishes the version to
send back as an `ETag` on every response that returns one versioned record, and
refuses a write aimed at a superseded version.

**The desktop sends it** on customers, vendors, products, branches, warehouses
and quotations, as of 2026-08-15. The version rides in the response body as
well as the ETag header — a list carries many records and a header carries one,
and this client edits from list rows — so the save carries the version of the
record the user opened.

**What the refusal says depends on where the editor saves from**, and 9.1c is
the case that checks it:

- **Customers and products** save from **inside** the dialog, so a refusal
  leaves the form on screen still holding every keystroke. The message says so.
- **Vendors, branches, warehouses and quotations** close the dialog and save
  after, so the typing is already gone. Those say the changes were **not
  saved** — claiming otherwise would be a lie the user acts on.

**Screens that still save last-one-wins**: UOM, tax, batches and serials,
territories, inventory, opening stock, physical counts, document types and
business profiles. 9.1e is the control case for those.

| ID | Case | Steps | Expected |
| --- | --- | --- | --- |
| 9.1 | Two users edit one customer | Open the same customer on two machines, save on A, then save on B | **B is refused**, and the message says somebody else saved it, that B's changes are still in the form and have not been sent, and to copy anything needed before closing |
| 9.1c | The refusal tells the truth about the typing | Run 9.1 on a **customer** (saves inside the dialog), then on a **vendor** (dialog closes first) | The customer message says the changes are **still here and have not been sent**; the vendor message says they were **not saved**. Neither should claim the other |
| 9.1e | The same race where the header is not sent yet | Repeat 9.1 on **UOM units** or **territories** | B **succeeds and overwrites A**, silently. That is still the behaviour on the screens listed above — record it, do not file it |
| 9.1a | The precondition the server owes **(HTTP)** | `GET /api/v1/customers/{id}` and note the `ETag`. `PUT` the same customer twice, sending `If-Match: <that etag>` both times | The first `PUT` returns 200 with a **new** `ETag`; the second is refused **409** with "This record changed since you loaded it" |
| 9.1b | The published version is the one that works **(HTTP)** | Repeat 9.1a's second `PUT`, this time sending the `ETag` the first `PUT` returned | 200. A client that echoes the header it was last given is never wrongly refused — it must not compute the next version itself |
| 9.1c | No precondition is still accepted **(HTTP)** | `PUT` the same customer with no `If-Match`, then again with `If-Match: *` | Both 200. `*` means "any version", which is the same as sending nothing |
| 9.1d | A malformed precondition is rejected, not ignored **(HTTP)** | `PUT` with `If-Match: banana` | 422. Silently ignoring it would give a client the protection it asked for in name only |
| 9.2 | Reload after a conflict **(HTTP)** | Continue 9.1a: `GET` the customer again, take the new `ETag`, and `PUT` with it | Succeeds |
| 9.3 | Same document, two approvals | Approve the same order on both machines at once | One succeeds, one is refused clearly. Never approved twice, never double stock movement |
| 9.4 | Stock race | Two machines dispatch the same stock simultaneously | Stock never goes negative without an explicit allowance |
| 9.5 | List refresh | Create a record on A; refresh the same list on B | It appears |

The six endpoints carrying an `ETag` are the `GET` and `PUT` pair for firms,
purchase orders, sales orders, delivery notes, goods receipts and customers.
9.1a–9.2 are written against customers because that update replaces the whole
address and contact collection, so the loser of a race does not merge badly —
they lose every row they entered.

```bash
# 9.1a, against the seeded WHOLE01 firm. See .claude/skills/run-app for $TOKEN.
ETAG=$(curl -s -D - -o /dev/null "$BASE/api/v1/customers/$ID" \
  -H "Authorization: Bearer $TOKEN" -H "X-Firm-ID: $FIRM" \
  | grep -i '^etag' | cut -d' ' -f2 | tr -d '\r')

curl -s -o /dev/null -w '%{http_code}\n' -X PUT "$BASE/api/v1/customers/$ID" \
  -H "Authorization: Bearer $TOKEN" -H "X-Firm-ID: $FIRM" \
  -H "Content-Type: application/json" -H "If-Match: $ETAG" -d @customer.json
# first call 200, same command again 409
```

---

## 10. Licence feature

> **Status: not implemented.** A `LICENSE_MANAGE` permission, a `LICENSE_ADMIN`
> role and a `license_error` error code exist; nothing uses them. There is no
> licence model, endpoint or screen.
>
> These cases are drafted so the feature is specified before it is written. They
> are **not executable today** and must not be reported as failures.

Questions to settle before building it — each changes the test cases:

1. What is licensed: the installation, the firm, the user, or a module?
2. What happens at expiry — read-only, blocked writes, or a grace period?
3. Does it need to phone home, or is it an offline key? Offline suits a
   low-specification on-premises Windows box with no guaranteed internet.
4. Who may see and enter a licence key — platform admin only, or a firm admin?
5. How is it stored so a determined user cannot simply edit it?

| ID | Case (draft) | Expected |
| --- | --- | --- |
| 10.1 | Fresh install with no licence | Behaviour is defined and clearly communicated — trial, read-only, or blocked. Not a crash and not silent full access |
| 10.2 | Enter a valid key | Accepted; the UI shows what is licensed and until when |
| 10.3 | Enter an invalid or corrupted key | Refused with a clear message; prior state unchanged |
| 10.4 | Key for a different installation | Refused |
| 10.5 | Expired licence | The behaviour chosen in question 2, applied consistently — and reads should stay possible so a firm can always get its data out |
| 10.6 | Expiry approaching | Warned in advance, with enough notice to act |
| 10.7 | Limit reached (firms or users, if licensed that way) | Refused when adding one more, naming the limit |
| 10.8 | Clock moved backwards | Moving the machine clock back does not extend the licence |
| 10.9 | Licence with no internet | Works offline if the design says it should |
| 10.10 | Two UIs, one licensed backend | Both clients see the same licence state |

---

## 11. Low-specification Windows behaviour

The target is a low-configuration Windows machine, so these are requirements,
not niceties. Record numbers, not impressions.

| ID | Case | Measure |
| --- | --- | --- |
| 11.1 | Cold start | Time from launching the client to the login screen |
| 11.2 | Login to workspace | Time from submitting credentials to a usable workspace |
| 11.3 | Large list | Open a list with several thousand rows; time the first page and scrolling |
| 11.4 | Memory | Peak RAM of the client after 30 minutes of ordinary use |
| 11.5 | Backend memory | Peak RAM of the backend with several clients connected |
| 11.6 | Smallest supported screen | Run at 1366×768 and visit every screen | No horizontal scrolling of the page, no clipped content, no overflow stripes |
| 11.7 | Slow network | Add latency between UI and backend | The UI stays responsive and shows progress rather than freezing |
| 11.8 | Client machine sleeps | Sleep and wake the client machine | The session recovers or asks for login cleanly |

---

## 12. Things that look like bugs and are not

Give this section to anyone testing for the first time.

- **A refusal naming a business-profile feature** (§6) is the gate working. Check
  the firm's profile before reporting.
- **A 403 rather than a validation error** on a gated field is deliberate: the
  payload is fine, the firm is not entitled to that field.
- **FOOD01 and MEDI01 sharing a schema** is by design. They must not share
  *data*; sharing tables is expected.
- **An audit log that does not show another firm's activity** is correct. Trails
  are per firm store; no single screen shows everything.
- **A credit warning that still lets the document through** is correct unless the
  firm's policy is set to Block.
- **`platform-admin` unable to open firm screens without choosing a firm** is
  correct.
- **Sales → Call Lists showing "Not today" for every plan** usually means the
  date is simply not the weekday the plan runs on. The screen opens on today;
  step it with the arrows.
- **A beat plan reporting "The route is not in force on this date"** is the
  route's effective window, not a broken plan. Check Runs from / Runs until on
  the territory editor.
- **Sales → Places being read-only** is correct for a firm login. Geography is
  shared reference data; only a platform administrator writes it.
- **"On no route yet" returning nothing** in WHOLE01 is correct — the seeder
  places every customer on a round. Create a customer to see the filter work.
- **The same shop appearing on two routes** is expected. A distributor calls one
  outlet on a sales beat and a collection round; only one of them is primary,
  and that is the one a sale is filed under.
- **A place dropdown reading "Currently set (not listed)"** is the record
  pointing at a place that is no longer offered — retired, or on a rung whose
  parent has changed. It is kept deliberately: dropping it would make the form
  save as blank and quietly lose a value nobody could see. Pick a new place, or
  leave it alone.
- **A place dropdown that is empty with a hint about Sales → Places** means the
  firm's geography masters have nothing at that rung, not that the form is
  broken. The record must still save — reference data nobody has filled in is a
  configuration gap, not a refusal.
- **A rung that will not open until the one above it is chosen** is intended.
  The list is loaded per parent; a flat list of every locality in the country is
  not a dropdown anybody can use.

---

## 13. Reporting

A useful report has: the case ID, what you did, what you expected, what happened,
the exact message, the `requestId`, the firm and its storage mode, the account
and its role, and whether it reproduces.

The firm's storage mode matters more than testers expect. A defect that appears
only in `DATABASE` mode, or only for the two firms sharing a schema, is a
different defect from one that appears everywhere — and that detail has been the
fastest route to the cause more than once in this codebase.
