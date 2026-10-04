# Signing in, sessions and your own account

Part of the QA test suite in `docs/qa/` for **release 1.3.0**, the first
end-to-end test pass (it includes 1.2.0). Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Every menu
path is the 1.3.0 menu: `Sell > Quotations` is the Sell drop-down on the menu
bar, `Sell > All Sell screens > Documents > Proforma` is a screen that is not
daily work, and `Settings > Set up > Pricing > Price Lists` is the gear at the
right of the bar. Generated on 2026-10-04 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Signing in, sessions, and the life of an account

A refusal about the **credential** says only "Invalid email or password." —
for a wrong password and for an unknown address alike, and at the same cost,
so nobody learns which addresses exist. A refusal about the **account's
state** — locked, inactive, expired — names the state and the remedy
(`docs/BACKLOG.md` 18.1, 18.2). Five wrong passwords lock an account for
fifteen minutes.

### TC-SESS-001 — Switching firms reloads every list

- **Preconditions:** The platform administrator, and one customer in each of two firms, QA01 and QA02. (a customer of yours in QA01 and another in QA02.)
- **Steps**
  1. Sign in as the prepared **Platform admin**; switch into **QA01** → Masters > Customers; search `QA`.
  2. With the list open, switch to **QA02**.
- **Expect:** step 1 shows `QA-ONE`; after the switch the list reloads by itself and shows `QA-TWO` — **no row from QA01 survives**, not even for a moment.
### TC-SESS-002 — An idle session refreshes quietly, and a signed-out one leaves nothing behind

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. Sign in as the prepared **Firm admin**; open Masters > Customers. Leave the application idle for **more than 15 minutes** (the access token's lifetime, `AGENCY_JWT_ACCESS_TOKEN_MINUTES`).
  2. Click **Refresh**.
  3. Sign out; press the mouse's Back button or Alt+Left.
- **Expect**
  - Step 2: the list reloads; you are **not** asked to sign in again — the client refreshes once on a 401 and repeats the request.
  - Step 3: the sign-in screen stays; no cached screen is reachable.
### TC-SESS-003 — Wrong passwords, a lockout, and a lock that counts down

- **Preconditions:** The platform administrator, a firm administrator of QA01, and an ordinary QA01 user to act on.
- **Steps**
  1. On the sign-in screen, try `nobody.qa@qa.test` / `Wrong@Password1`.
  2. Try the prepared **Target** with `Wrong@Password1` **four** times.
  3. A fifth time.
  4. Now the prepared password (the right one).
  5. Watch the banner.
- **Expect**
  - Steps 1–2: "Invalid email or password." every time, the unknown address included, and each takes **about as long** as the others (~2 seconds on this machine, measured) — a wrong address and a wrong password must not feel different.
  - Step 3: "This account is locked after too many failed sign-in attempts. You can try again in 15:00." and the clock **counts down** a second at a time.
  - Step 4: refused the same way, with the time left. The lock is checked before the password is.
  - Step 5: at zero, "The lock on this account has lifted. You can sign in now." *(If you cannot wait, TC-SESS-004 lifts it.)*
### TC-SESS-004 — A firm administrator clears a lock

- **Preconditions:** The platform administrator, a firm administrator of QA01, and an ordinary QA01 user to act on.
- **Steps**
  1. Lock the prepared **Target** with five wrong passwords (TC-SESS-003 steps 2–3).
  2. Sign in as the prepared **Firm admin** → Settings > Platform > People > Users → Edit **Lock Target (qa)** → tick **Clear login lock (Account Lock)** → Save.
  3. Sign in as the target with the prepared password.
- **Expect:** step 3 signs in at once — the lock cleared and the failed count reset. *(2.9's other way, waiting fifteen minutes, ends the same; TC-SESS-003 step 5 shows it.)*
### TC-SESS-005 — Inactive and expired accounts are told why

- **Preconditions:** The platform administrator, a firm administrator of QA01, and an ordinary QA01 user to act on.
- **Steps**
  1. As the prepared **Firm admin**, Settings > Platform > People > Users → Edit the target → untick **Active** → Save. Sign in as the target with the right password; then with `Wrong@Password1`.
  2. Edit again: tick Active, set **Expires at** to yesterday → Save. Sign in with the right password; then a wrong one.
  3. Clear Expires at → Save; sign in.
- **Expect**
  - Step 1, right password: "This account is inactive. Ask an administrator to reactivate it." Login history says `account_unavailable`.
  - Step 2, right password: "This account has expired. Ask an administrator to extend it."
  - Step 3: signs in.
  - **With a wrong password, all three answer "Invalid email or password."** — the state is named only to somebody who typed the right one. Fixed 2026-09-16; see defect **D-2-1**.
### TC-SESS-006 — A password somebody else set must be changed

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. As the prepared **Firm admin**, Settings > Platform > People > Users → New: `qa.newbie@qa.test`, password `Welcome@123456`, **Require password change** on, in QA01 → Save.
  2. Sign in as them. On the change-password screen try new passwords `Short@1`, then `LongEnoughPassw0rd`, then `Newbie-Passw0rd!`.
- **Expect:** the change-password screen and nothing else reachable. `Short@1` refused ("Use at least 12 characters."); `LongEnoughPassw0rd` refused ("Include a symbol."); `Newbie-Passw0rd!` accepted and the app opens.
### TC-SESS-007 — Deleting somebody releases their address; the new account is a new person

- **Preconditions:** The platform administrator, a firm administrator of QA01, and an ordinary QA01 user to act on.
- **Steps**
  1. As the prepared **Platform admin**, Settings > Platform > People > Users → select the target → **Delete**.
  2. Settings > Platform > People > Users → New with the same email, any name and password, no firms or roles → Save.
- **Expect:** step 1 — gone from the grid; Settings > Platform > System > Audit Logs keeps the row. Step 2 — the address is accepted again (soft delete releases it) and the new account has **no** roles and **no** firms.
### TC-SESS-008 — Restoring a deleted person as they were

- **Preconditions:** The platform administrator, a firm administrator of QA01, and an ordinary QA01 user to act on.
- **Steps**
  1. As the prepared **Platform admin**, delete the target. Settings > Platform > People > Users → **Status** filter → **Deleted** → open them.
  2. **Restore** (dialog footer). Sign in as the target with the prepared password.
  3. Delete the target again; create a **new** account with the same address; Status → Deleted → open the old one → Restore.
- **Expect**
  - Step 1: status **Deleted**, Edit and Delete dead, View opens.
  - Step 2: back in the grid with QA01 and SALES_EXECUTIVE; the old password works.
  - Step 3: refused — "Another live account now holds this email address. Delete that account first if this is the one to keep." Restore before re-onboarding, not after.
### TC-SESS-009 — Deleted people are a platform administrator's; inactive ones anybody's

- **Preconditions:** The platform administrator, a firm administrator of QA01, and an ordinary QA01 user to act on.
- **Steps**
  1. As the prepared **Firm admin**, Settings > Platform > People > Users → open the **Status** filter.
  2. **(HTTP)** As the firm admin, `GET /api/v1/users?deleted_only=true&search=qa`.
  3. Edit the target: untick **Active** → Save. Status → **Inactive**.
  4. As the prepared **Platform admin**: Status → **Inactive**; then also pick the firm **QA01**.
- **Expect**
  - Step 1: Active and Inactive, **no Deleted**; and no **Restore** anywhere. A deleted person's memberships still place them in a firm, and a firm's grid must not list them.
  - Step 2: **live** rows only — the flag is ignored for a firm caller.
  - Step 3: the target, and nobody active.
  - Step 4: the switched-off people from every firm, the target among them and no deleted ones; with QA01 as well, only QA01's inactive people.
### TC-SESS-010 — Who may not be deleted

- **Preconditions:** The platform administrator, a firm administrator of QA01, a user who is a member of QA01 and QA02, and a user in QA02 only. ((for the shared person) and `platform-admin-member` (for a platform administrator to aim at))
- **Steps**
  1. As the `shared-member` preparation's **Firm admin**, Settings > Platform > People > Users → select **Shared Member (qa)** → Delete.
  2. **(HTTP)** As any platform administrator, `DELETE /api/v1/users/{id of the platform-admin-member preparation's admin}`.
- **Expect**
  - Step 1: refused — "This person also works in another firm, so their profile is managed by a platform administrator. You can still set their roles and job template in your own firm."
  - Step 2: **422**, "Platform administrator users cannot be deleted."
### TC-SESS-011 — Setting somebody else's password

- **Preconditions:** The platform administrator, a firm administrator of QA01, and an ordinary QA01 user to act on.
- **Steps**
  1. Lock the target (five wrong passwords).
  2. As the prepared **Platform admin** → Settings > Platform > People > Users → open the target → **Reset password** (dialog footer) → `Temp-Passw0rd!!`, "Require a new password" on → Save. Sign in as the target with it.
  3. Reset again to `Handover-Passw0rd!` with "Require a new password" **off**; sign in with it.
  4. As the platform admin, open **your own** row → Reset password.
  5. As the prepared **Firm admin**, open the target.
- **Expect**
  - Step 2: the lock is gone — they sign in at once and land on the change-password screen. Any other window of theirs is signed out.
  - Step 3: the app opens straight away: a handover, the password theirs to keep.
  - Step 4: refused — "Change your own password from My profile, where the current one is asked for."
  - Step 5: **no Reset password** in the footer. **(HTTP)** `POST /api/v1/users/{id}/password` as the firm admin → **403**.

## Platform mode — the switcher and what a platform administrator starts on

A platform administrator with reach over every firm, and a member of none, used
to get a token carrying every code — so the menu offered Sell and
Stock — and an empty firm switcher, so every one of those screens refused
its first request. The firm switcher is now the mode switch: **Platform** is
one of its entries.
### TC-PLAT-001 — A platform administrator starts on Platform, every time

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps**
  1. Sign in as the prepared **Platform admin**.
  2. Read the firm control in the header, and the status bar.
  3. Switch into **QA01** (see TC-PLAT-003), then sign out and sign back in.
- **Expect**
  - Steps 2 and 3: the header firm control reads **Platform**, and so does the status bar — **including after having been in QA01**.
  - That is deliberate: somebody with reach over every firm's books must not land silently in one of them on a screen that looks like their own. `SessionController.resolveLandingFirm` returns no firm for any platform administrator, whatever their last firm or primary.
### TC-PLAT-002 — Platform mode offers the platform, and nothing that needs a firm

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps**
  1. Sign in as the prepared **Platform admin**. The header reads **Platform**.
  2. Read the menu bar. Click the gear and read its three parts.
- **Expect** — taken from the desktop's own visibility and menu logic:

  | Where | Screens inside |
  | --- | --- |
  | **Menu bar** | Home and the gear only (no firm is chosen) |
  | **Settings > Platform > People** | Users · Roles · Permissions · User Templates · User-Firm Assignments |
  | **Settings > Platform > Firms** | Firms · Business Profiles |
  | **Settings > Platform > Agency** | Branding |
  | **Settings > Platform > System** | Audit Logs · Diagnostics · Licensing · Backups · Platform Dashboard |
  | **Settings > This PC and me** | My Preferences |

  **No** Sell, Buy, Stock, Accounts, Masters or Reports menu, and none of the firm's own Settings (Numbering Series, Tax, Units of Measure, Industry Templates ...) — those live in a firm's own store and need a firm.
- **Why:** `requiresFirm` on a module *and* on a tab hides what needs a firm when none is selected. A platform administrator's token carries every code, so permissions alone would offer everything.
### TC-PLAT-003 — The switcher lists every firm, and choosing one grows the workspace

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps**
  1. Sign in as the prepared **Platform admin**.
  2. Open the firm control.
  3. Pick **QA01**.
  4. Open **Sell > Sales Orders**.
  5. Open the firm control again and pick **Platform**.
- **Expect**
  - Step 2: a **Platform** entry at the top with a tick beside it, then **every active firm** — QA01, QA02, WHOLE01, ELEC01, MEDI01, FOOD01 among them — **although this account is a member of none**.
  - Step 3: a notification names QA01. The menu bar grows **Sell, Buy, Stock, Accounts, Masters, Reports**, and the Settings page gains the firm's own parts (Firm, Selling, Buying, Stock, Tax, Business profile and SET UP). **Licensing goes away** — it is a platform screen.
  - Step 4: the screen **loads** with no error — whatever orders preparations have raised in QA01, or none. Before the fix this module was offered and this screen failed.
  - Step 5: **"Working on the platform. No firm is selected."** The firm-owned modules go away again.
### TC-PLAT-004 — Being a member of firms does not change where a platform administrator lands

- **Preconditions:** A platform administrator who is also a member of QA01 and QA02.
- **Steps**
  1. Sign in as the prepared **Platform admin** — this one *is* a member of QA01 (primary) and QA02.
  2. Read the header; open the firm control.
- **Expect:** still starts on **Platform**. The switcher looks as in TC-PLAT-003, with QA01 marked **primary**. Membership is not what decides the landing; the designation is.
### TC-PLAT-005 — A firm user never sees Platform

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. Sign in as the prepared **Firm admin**.
  2. Read the header; open the firm control.
- **Expect:** **no Platform entry** anywhere; QA01 selected and the only firm; lands in it. For an ordinary user a null firm is an empty application rather than a mode, so the switcher refuses to offer it.
---

## The user menu — who you are, and where you start

`GET /api/v1/me` names the signed-in person; `PUT /api/v1/me/primary-firm`
and `POST /api/v1/auth/change-password` are theirs to call. All three need
being signed in and nothing else.

### TC-ME-001 — The menu names you, including after a restored session

- **Preconditions:** An ordinary user who is a member of QA01 and QA02, with a role in each.
- **Steps**
  1. Sign in as the prepared **Two-firm user** with **Remember me** ticked.
  2. Open the account menu (top right); read the status bar.
  3. Close the application and start it again.
- **Expect**
  - Step 2: the first row is the **full name** — `Two Firm User (qa)` — with the **email** under it. Not the address typed at sign-in, and not the word "User". The status bar shows the same name.
  - Step 3: still the name. It used to read "User", because a restored session never passes through the login form and the token carries no name.
### TC-ME-002 — Choosing your own primary firm

- **Preconditions:** An ordinary user who is a member of QA01 and QA02, with a role in each.
- **Steps**
  1. Sign in as the prepared **Two-firm user**.
  2. Account menu → **My preferences**.
  3. **Start in firm** → **QA02** → **Save**.
  4. Open the firm switcher.
- **Expect**
  - Step 2: the dialog opens at once, **Start in firm** reading **QA01** and listing only QA01 and QA02. The account menu has **no separate Primary firm entry** any more.
  - Step 3: the dialog closes. **Nothing on screen switches** — the primary is for next time, not for now.
  - Step 4: **QA02** is labelled `primary` beside its code.
### TC-ME-003 — Signing in lands in the primary firm, not the last one used

- **Preconditions:** An ordinary user who is a member of QA01 and QA02, with a role in each.
- **Steps**
  1. Sign in as the prepared **Two-firm user** (primary: QA01).
  2. Switch to **QA02** and open any screen there.
  3. Sign out, sign back in.
- **Expect:** you land in **QA01**, the primary — not QA02, where you were last. Switching is for the session; the primary is for next time. Until 2026-09-08 it was the reverse, so the flag meant nothing to anybody who had ever switched.
### TC-ME-004 — Nobody can make a firm they do not belong to their primary

- **Preconditions:** An ordinary user who is a member of QA01 and QA02, with a role in each.
- **Steps (HTTP)** — sign in as the prepared user and send:
  ```
  PUT /api/v1/me/primary-firm
  { "firm_id": "<the id of a firm this account does not belong to>" }
  ```
  Get that id as a platform administrator, from `GET /api/v1/firms`, choosing one this account is not a member of.
- **Expect:** **422**, "You can only make a firm you belong to your primary firm." Nothing changes.
### TC-ME-005 — My profile, for somebody who cannot read the user list

- **Preconditions:** An ordinary user who is a member of QA01 and QA02, with a role in each. (holds `SALES_EXECUTIVE` and `CUSTOMER_SUPPORT`, neither of which carries `USER_VIEW`.)
- **Steps**
  1. Sign in as the prepared **Two-firm user**.
  2. Account menu → **My profile**.
- **Expect**
  - Opens. Name and email at the top; sections **Work**, **Contact**, **Firms**, **Access** and **Sign-in**; every unset field reads **Not set**.
  - **Firms:** QA01 marked **Primary**, and QA02.
  - **Access:** roles grouped as **In every firm** (Customer Support) and **In QA01** (Sales Executive).
  - No boxes to type in, and the line: *"These details are held by your administrator. Ask them to change anything here; your appearance, primary firm and password are yours to set."*
### TC-ME-006 — A platform administrator's menu

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps**
  1. Sign in as the prepared **Platform admin**.
  2. Open the account menu; open **My profile**.
- **Expect:** the menu offers **My preferences**, and the dialog has **no Start in firm** box — a platform administrator always starts on Platform, so there is nothing to choose. My profile shows a **Platform administrator** chip under the name.
### TC-ME-007 — Somebody in one firm has no primary to choose

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** sign in as the prepared **Firm admin**, open the account menu → **My preferences**.
- **Expect:** **no Start in firm** box. It is offered only to somebody with more than one firm who is not a platform administrator.
### TC-ME-008 — Changing your own password

- **Preconditions:** An ordinary user who is a member of QA01 and QA02, with a role in each.
- **Steps**
  1. Sign in as the prepared **Two-firm user** — in **two windows** if you want to see the second one signed out.
  2. Account menu → **My profile** → **Change password**.
  3. New password `Short@1` (under twelve characters).
  4. New password `LongEnoughPassw0rd` (no symbol).
  5. Current password `Wrong@Password1`, new password `Str0ng-Passw0rd!` twice.
  6. Current password: the prepared password, new password `Str0ng-Passw0rd!` twice.
- **Expect**
  - Step 3: refused beside the box, **"Use at least 12 characters."** — nothing sent.
  - Step 4: **"Include a symbol."** — nothing sent. (The desktop checks the same rules the server enforces: twelve characters, upper, lower, digit, symbol.)
  - Step 5: the server's refusal in the dialog — **"Current password is incorrect."** — and the dialog **stays open** for another try.
  - Step 6: both dialogs close and you land on the login screen with **"Password changed. Sign in with your new password."** The other window is signed out on its next click. Sign in with `Str0ng-Passw0rd!`.
  - No need to set it back: the account is yours.
### TC-ME-009 — My preferences: theme, text size and date format apply at once

- **Preconditions:** An ordinary user who is a member of QA01 and QA02, with a role in each.
- **Steps**
  1. Sign in as the prepared **Two-firm user**; open any sales invoice and note how its date is written.
  2. Account menu → **My preferences**. Change nothing → **Save**.
  3. Open it again: **Theme** → **Dark**, **Text size** → **Large**, **Date format** → the `yyyy-MM-dd` row → **Save**.
  4. Open the same sales invoice again.
  5. Open My preferences, change the theme, then press **Esc**.
  6. Sign out, sign in on **another PC** (or another Windows account) as the same user.
- **Expect**
  - Step 1: dates read `dd-MM-yyyy` (for example `04-10-2026`) — the default for everybody after the 1.2.0 upgrade.
  - Step 2: the dialog closes; nothing changes.
  - Step 3: the dialog closes and, without restarting, the screen turns dark and the text grows. Each date-format row shows today's date written that way.
  - Step 4: the invoice date now reads `2026-10-04` style.
  - Step 5: the dialog closes and the theme stays as it was.
  - Step 6: the dark theme and the `yyyy-MM-dd` dates follow the user; **text size does not** — it is this PC's setting, and the dialog says *This PC only*.
### TC-ME-010 — My preferences: the first screen

- **Preconditions:** An ordinary user who is a member of QA01 and QA02, with a role in each.
- **Steps**
  1. Sign in as the prepared **Two-firm user**. Account menu → **My preferences** → open the **First screen** list.
  2. Choose Sell > **Sales Invoices** → **Save**.
  3. Open Customers, then sign out and back in.
  4. Set **First screen** back to **The screen I was last on**; open Customers; sign out and back in.
- **Expect**
  - Step 1: the first entry is **The screen I was last on** (selected); below it only screens this user's roles may open — no Users, Roles or Firms.
  - Step 3: you land on **Sales Invoices**, not Customers.
  - Step 4: you land on **Customers**, where you were last.
### TC-ME-011 — Favourites: star a screen, find it on Home and in Ctrl+K

- **Preconditions:** An ordinary user who is a member of QA01 and QA02, with a role in each.
- **Steps**
  1. Sign in as the prepared **Two-firm user**. Open **Sell**; point at **Sales Orders** and click the star that appears. Star one more screen in another drop-down.
  2. Go to **Home**.
  3. On Home, drag the last favourite before the first; point at another box and click its **x**.
  4. Press **Ctrl+K** and type `s`.
  5. Sign out; sign in on another PC (or another Windows account) as the same user.
- **Expect**
  - Step 1: each star turns gold as it is clicked; the drop-down stays open.
  - Step 2: the **FAVOURITES** box shows the starred screens.
  - Step 3: the order changes and the removed box goes; that screen's star in its drop-down is no longer gold.
  - Step 4: starred screens are listed **first** among the matches.
  - Step 5: the same favourites, in the same order.
### TC-ME-012 — The light menu: daily work first, everything one click away

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. Sign in as the prepared **Firm admin**. Open **Sell**.
  2. Click **Returns & notes**.
  3. Click **All Sell screens** at the foot.
  4. Open **Buy**, **Stock**, **Accounts** and **Masters** the same way.
  5. Look along the menu bar for **Admin**.
- **Expect**
  - Step 1: a short list — Quotations, Sales Orders, Delivery Notes, Sales Invoices, Returns & notes, Receipts, Customer Statements — and **All Sell screens (N)** at the foot. Price Lists, Promotions and Territories are **not** here.
  - Step 2: a short list beside it: Sales Returns, Credit Notes, Customer Debit Notes.
  - Step 3: every Sell screen this user may open, under its group (Documents, Money, Incentives, Insight, Field sales); any of them opens in a tab.
  - Step 4: each area works the same way; Masters shows Customers, Vendors, Products, Branches and Warehouses, and its lists (Customer Groups, Product Categories, Units, Places …) are under Settings > Set up.
  - Step 5: **no Admin** on the bar: Users, Roles, Firms, Audit Logs and Backups are under **Settings > Platform**, for those who may open them.
### TC-ME-013 — Settings > Set up: cards and a search across every section

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template). (, then `two-firm-user`)
- **Steps**
  1. Sign in as the prepared **Firm admin**. Click the **gear**.
  2. Click **This PC and me**, then the **My Preferences** card.
  3. Close it; in the search box type `price`.
  4. Click **Price Lists**.
  5. Sign in as the **Two-firm user** and click the gear.
- **Expect**
  - Step 1: Settings opens as a tab: sections down the left — This PC and me, Firm, Selling, Buying, Stock, Tax, Business profile, then **SET UP** (Pricing, Territories & routes, Account structure, Party lists, Item lists, Locations) and, for a platform administrator only, **PLATFORM**; the chosen section's screens as cards.
  - Step 2: the My preferences dialog opens.
  - Step 3: matches from every section — Price Lists, Price Levels, Price Floor …
  - Step 4: Price Lists opens in its own tab.
  - Step 5: only the sections this user's roles reach; **This PC and me** is always there.
### TC-ME-014 — The sign-in screen shows the agency, and the strengths cycle

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. Open the app on a PC whose server has the agency's branding set (give it first under Settings > Platform > Agency > Branding if not). Do not touch the sign-in boxes for 20 seconds.
  2. Click the next and previous arrows and a dot on the left panel.
  3. Type one letter in the email box.
  4. Narrow the window below 900 px wide.
  5. Read the foot of the sign-in card, the window's title bar and the status line.
- **Expect**
  - Step 1: the agency's logo (or the initials of its name), name and tagline sit above the form; a night-blue panel on the left shows one strength with a title and a line, and changes to the next about every 8 seconds.
  - Step 2: the panel moves one strength at a time; the dot shows where you are.
  - Step 3: the panel stops cycling for good, even after the box is cleared, until the app is reopened.
  - Step 4: the left panel goes and the sign-in card stands alone, nothing cut off.
  - Step 5: the product mark (Agency Platform, "by" its company and tagline) is in the card's foot; the title bar reads **Agency Platform - Sign in**; the status line shows the server state, the version and *Powered by Agency Platform*.
### TC-ME-015 — Sign-in: More help, Copy details for support, and a server that does not answer

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. On the sign-in screen open **More help**.
  2. Click **Copy details for support** and paste into Notepad.
  3. Stop the server (or open Application Settings and point the API URL at a port nothing listens on), then close and reopen the app.
  4. Start the server again, reopen the app.
- **Expect**
  - Step 1: support rows (phone, WhatsApp, hours, email, website) each appear only if filled -- they are blank in this release, so none shows; the line *Forgot your password? Your administrator resets it.* does.
  - Step 2: the button says it copied; the text names the product, its version, the server address and this computer's name. No password or token is in it.
  - Step 3: the sign-in screen still opens at once, showing the agency's name, tagline and logo from this PC's last answer (or Agency Platform's own name and logo if this PC never had one); no error box.
  - Step 4: the agency's current branding shows.
### TC-ME-016 — First sign-in: Set up your agency, Skip for now, and the Home card

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. On an installation whose branding has **not** been set (a fresh install with the Branding page left blank), sign in as the platform administrator.
  2. Press **Skip for now**.
  3. Look at Home, then click **Set up your agency** on the card.
  4. Leave the name blank and press **Save**; then type `QA Book Traders Agency`, a tagline `Quality in bulk`, choose a PNG under 1 MB as the logo and press **Save**.
  5. Sign out and sign in again; look at the top of the window and Home.
  6. Sign in as the firm administrator instead.
- **Expect**
  - Step 1: a dialog **Set up your agency** opens over Home with Agency name, Tagline, Logo and a live preview.
  - Step 2: the dialog closes and nothing is saved.
  - Step 3: Home shows a **Finish setting up** card (*Give your agency's name and logo, so every PC shows them.*); the button opens the same form.
  - Step 4: a blank name is refused beside the box; the full save closes the form and the card disappears from Home.
  - Step 5: the dialog no longer opens; the agency's logo, name and tagline lead the menu strip; the window title reads the agency name.
  - Step 6: no dialog and no card appear for a person without platform settings rights.
### TC-ME-017 — Settings > Platform > Agency > Branding: change, logo rules, two people at once

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. Sign in as the platform administrator. Open **Settings > Platform > Agency > Branding**.
  2. Change the tagline and watch the preview; press **Save**.
  3. Press **Choose logo** (or **Change logo**) and pick a file named `fake.png` that is really a text file; then a PNG or JPG larger than 1 MB.
  4. Choose a valid square PNG; Save. Then press **Remove logo**; Save.
  5. On two PCs (or two windows) open the page; on the first change the tagline and Save; on the second change the name and Save.
  6. Sign in as the firm administrator and open Settings.
- **Expect**
  - Step 1: name, tagline, logo, a preview of the sign-in card and of the top of every screen, and our product and company read-only (*set by the installer; changed only by an update*). There is no colour box.
  - Step 2: the preview follows each keystroke; Save shows *Saved.*; the menu strip changes at once with no refresh.
  - Step 3: the text file is refused with *The logo must be a PNG or JPG image.* (the file's contents are judged, not its name); the large one with a message that it is N MB and the limit is 1 MB. The form keeps everything typed.
  - Step 4: the logo appears in the preview and the header; after Remove, the initials of the name show instead.
  - Step 5: the first save succeeds; the second is refused inside the form with the somebody-else-saved message and keeps what was typed.
  - Step 6: **Platform** and its Agency group are not offered.
### TC-ME-018 — The header: agency and firm, narrow window, Home, status line

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. Sign in as the firm administrator of a firm, with the agency's branding set. Look at the menu strip and the window's title bar.
  2. Switch firm with the firm switcher (if there are two); then sign in as the platform administrator, who has no firm chosen.
  3. Narrow the window to under 820 px, then widen it past 1280 px.
  4. Open Customers, then click the agency's logo or name at the left of the strip.
  5. Read the right end of the status line and point at it.
- **Expect**
  - Step 1: the logo, name and tagline lead the strip before Home, then the firm's name as plain text; the title bar reads **<agency> > <firm>**.
  - Step 2: the firm part of the title follows the switch; with no firm the title is the agency's name alone.
  - Step 3: below 820 px only the logo shows; the tagline appears from 1280 px.
  - Step 4: Home opens.
  - Step 5: the product's mark, *Agency Platform <version> by <company>*, and a tooltip with the same words. Clicking it does nothing (there is no About screen yet).
---

## User tiers — what a platform operator may and may not reach

Four kinds of user, not interchangeable:

| Tier | Who | Reaches |
| --- | --- | --- |
| 1 | Platform operator (`PLATFORM` scope) | Creates firms and their people, provisions storage, sets a firm up. **Refused a firm's books.** |
| 2 | All-firms administrator (`ALL_FIRMS` scope) | Everything, in every firm, with no membership needed — see TC-PLAT-001..004. |
| 3 | Firm administrator (`FIRM_ADMIN`) | Everything inside their own firm, including its people. |
| 4 | Firm staff | The modules their job needs. |
### TC-TIER-001 — A platform operator runs the platform

- **Preconditions:** A platform administrator with **PLATFORM** scope (not ALL_FIRMS) who is a member of QA01 and QA02 with no roles. Creating one needs the platform designation set on the account; ask the developer if the screen offers no way to do it.
- **Steps**
  1. Sign in as the prepared **Operator**. The header reads **Platform** — where every platform administrator lands.
  2. Click the gear and open, under **Platform**: People > **Users**, **Roles**, **Permissions**, **User Templates**, **User-Firm Assignments**; Firms > **Firms**, **Business Profiles**; System > **Platform Dashboard**, **Audit Logs**, **Diagnostics**.
- **Expect:** every one offered, and each opens. Running the platform is their job.
### TC-TIER-002 — A platform operator is refused the books, even where they are a member

- **Preconditions:** A platform administrator with **PLATFORM** scope (not ALL_FIRMS) who is a member of QA01 and QA02 with no roles. Creating one needs the platform designation set on the account; ask the developer if the screen offers no way to do it.
- **Steps**
  1. Sign in as the prepared **Operator**. Look along the menu bar for Sell, Buy, Stock, Accounts and Masters.
  2. Open the firm switcher.
  3. Switch into **QA01** and read the menu bar.
- **Expect**
  - Step 1: **none** offered on Platform. Their token carries **33** codes — firm, user, role, permission, platform and system administration (`FIRM_*`, `USER_*`, `ROLE_*`, `PERMISSION_*`, `PLATFORM_VIEW`, `PLATFORM_SETTINGS`, `SETTINGS_VIEW`, `SETTINGS_UPDATE`, `AUDIT_LOG_VIEW`, `DIAGNOSTICS_VIEW`, `LICENSE_MANAGE`, `SYSTEM_BACKUP`, `SYSTEM_RESTORE`, `SYSTEM_CONFIGURATION`) and nothing operational.
  - Step 2: Platform, **QA01** (primary) and **QA02** — the two firms they are a member of, and **not** every firm. An `ALL_FIRMS` administrator is widened to every firm (TC-PLAT-003); a `PLATFORM` one is not, but memberships they genuinely hold still show.
  - Step 3: **no business modules**. A designation is a ceiling, not a floor, and they hold no role in QA01.
### TC-TIER-003 — The server agrees: no firm's books, all of the platform

- **Preconditions:** A platform administrator with **PLATFORM** scope (not ALL_FIRMS) who is a member of QA01 and QA02 with no roles. Creating one needs the platform designation set on the account; ask the developer if the screen offers no way to do it.
- **Steps (HTTP)** — sign in as the prepared operator:
  1. With `X-Firm-ID` of QA01: `GET /api/v1/customers`, `GET /api/v1/sales-orders`, `GET /api/v1/finance/journal-entries`.
  2. With no `X-Firm-ID`: `GET /api/v1/users`, `/api/v1/firms`, `/api/v1/roles`, `/api/v1/audit-logs`.
- **Expect**
  1. **403** on all three, "You do not have permission to perform this action." — although they are a member of QA01. Not a rule of its own: a `PLATFORM` administrator is simply not exempt from the membership check, and meets it holding no role.
  2. **200** on all four.
---

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
