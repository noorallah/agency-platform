# Logo, agency name and company name: findings for review

Prepared 2026-09-28 for the owner to review; **updated 2026-10-03** after the
owner asked for the agency's branding to be given during installation and for
placeholders for our own product and company. The build items are backlog §71
(`docs/BACKLOG.md`). On 2026-10-04 the owner asked for U1-U7 to be built now,
keeping the "Agency Platform" names until the Jugnix trademark is filed; see
**section 8** for what is built. The wireframes are
`dist\windows\Design\Branding wireframes.html` (section 6).

## 1. What the owner asked

1. A wireframe for the sign-in screen, with **two or more layouts** to choose
   from, following the Home page's look.
2. The **logo and agency name must be configurable**.
3. The logo and name must carry into the **main app after sign-in**, not only
   the sign-in screen.
4. Decide **when and how** they are provided: during installation, or later.
5. **Our own company name** must be visible somewhere.
6. Do it **the way market tools do it**.

## 2. What the app does today

- The phase 1 sign-in screen reads `config\branding.json` beside the
  executable: `app_name`, `company_name`, `logo_path`, two colours, the version
  and support contacts.
- That file lives on **each PC** and is edited by hand, so ten PCs mean ten
  edits. Setup overwrites it on upgrade, and nobody can change it from inside
  the app. The logo path must point at a file that exists on that PC.
- The phase 2 menu bar shows the fixed word "Agency" at its left.
- Our company name is a placeholder: `AppPublisher "Agency"` in
  `packaging/AgencyPlatform.iss` (the installer and Windows' Apps list) and
  `CompanyName "Agency"` in `desktop/windows/runner/Runner.rc` (the exe's
  properties).
- Each firm already has its own letterhead for printed documents; this work
  does not change it.

## 3. How market tools do it (checked 2026-09-28)

| Product | Customer's name and logo | When it is given | Maker's own name |
| --- | --- | --- | --- |
| **Odoo** | The login page logo comes from the company record (Settings > Companies); the company logo is used across the app and on reports | Any time after install, in Settings | "Powered by Odoo" under the login form |
| **Zoho Books** | Organisation logo uploaded under Settings > Organization Profile; used in the app, on transaction PDFs and on emails; can be per business location | Any time, in Settings | Zoho's name on the product and its menus |
| **Business Central** | Company name always at the top left (clicking it returns to the Role Centre); a company badge top right; the logo from Company Information on printed and emailed documents | Company Information page, any time | Microsoft Dynamics 365 Business Central on the product bar |
| **TallyPrime** | Company name asked when the **company is created**; shown on the gateway screen; the logo printed on invoices only if configured (Print > Configuration) | When creating the company, not at install | TallyPrime's name on every screen |

**What they all share:**

- **None asks for the customer's name in the installer.** The installer asks
  only technical questions.
- The customer's name and logo are given **inside the app**, by an
  administrator, and can be **changed any time**.
- The maker's name stays on the product (title, About, "Powered by" on the
  login page) and **stays off the customer's own invoices**.

Sources:
[Odoo login page logo](https://www.odoo.com/forum/help-1/how-to-edit-login-page-logo-204901),
[Zoho Books organisation profile](https://www.zoho.com/us/books/help/settings/organization-profile.html),
[Business Central company information](https://learn.microsoft.com/en-us/dynamics365/business-central/admin-company-information),
[Business Central company badge](https://yzhums.com/20817/),
[TallyPrime invoice with company logo](https://help.tallysolutions.com/tally-prime/sales-process/print-sales-invoice-with-additional-details/).

## 4. Proposal: three names, three owners

| Name | Example | Who sets it, and when | Where it shows |
| --- | --- | --- | --- |
| **The agency** (the customer who bought the product) | Sri Lakshmi Agencies | On the **server installer's Branding page** (optional); if left blank, the **first-run setup** asks after the first sign-in; changed any time in **Settings > Platform > Branding** | Sign-in screen; **left end of the menu bar on every screen**; window and taskbar title; "Licensed to" in About |
| **The firm** (the business being worked in) | QA01 Traders | As today, when the firm is created | Firm switcher, Home greeting, the firm's letterhead on printed documents (unchanged) |
| **Our company** (the maker) and **our product** | Jugnix / Jugnix Trade, shown as `[Company name]` / `[Product name]` with a placeholder logo until the trademark is filed | In the installer package's branding file; **locked at install** (approved 2026-10-03); **a new installer or an update installer can change any of them** -- company name, logo, tagline, product name -- so a rebrand ships as an update | Installer and Windows' Apps list as publisher; exe properties; "Powered by <product>" on sign-in; right end of the status line; Help > About |

### 4.1 The agency's branding

- **What:** agency name (required), tagline (optional), logo (optional; PNG or
  JPG, square, up to 1 MB; initials show when there is none), accent colour.
- **Held by the server**, in one platform-level record. There is one agency
  per installation, above its firms, because sign-in happens before a firm is
  chosen.
- **Read before sign-in** through a public, unauthenticated request (nothing
  secret in it). Each PC keeps a copy, so the logo still shows while the
  server is down.
- **Edited in Settings > Platform > Branding**, by platform administrators
  only, with a live preview. Every change goes into the audit trail. Other PCs
  pick it up at their next sign-in.
- **`branding.json` becomes the fallback.** It keeps the server address and
  the version; its name and logo apply only until the server's record is set,
  so an installation that set them by hand keeps them.

### 4.2 When it is given: on the server install, with the first-run setup as the fallback

Changed 2026-10-03 at the owner's request (the 2026-09-28 proposal kept it out
of the installer).

- The installer has six pages: 1. Welcome, 2. Server or client, **3. Branding**,
  4. Database, 5. Install folder, 6. Ready.
- **Page 3 appears on a server install only.** Agency name, tagline and logo,
  all optional, are written to the **server's** branding record, so every PC
  shows them. A client install never asks; it reads the server. (This answers
  the earlier objection: what is typed is not held on one PC.)
- The right half of page 3 shows our product name, company and product logo
  from the package, **locked** (owner approved the installer 2026-10-03; the
  "editable" reseller variant is not taken).
- After the **first administrator signs in for the first time**, a short setup
  opens: **1. Your agency** > **2. First firm** > **3. Users** > **4. Done**.
  If the installer took the branding it is shown filled in to check; if it was
  left blank it is asked here. It can be skipped; Home then shows a "Finish
  setting up" card until it is done.

### 4.3 After sign-in (the main app)

- **Menu bar, left end, every screen:** agency logo + name; clicking it goes to
  Home. Below 820 px wide only the logo shows.
- **Window and taskbar title:** "QA01 Traders - Sri Lakshmi Agencies".
- **Firm switcher:** the firm being worked in, as today.
- **Status line, right end:** "<product> 1.0.2 - <our company>".
- **Help menu:** keyboard shortcuts, user guide, contact support, About.

### 4.4 Our company's name

- Shown on the installer's welcome page and in Windows' Apps list as publisher,
  in the exe's properties, as "Powered by <product>" at the foot of the
  sign-in screen, at the right end of the status line, and in **Help > About**:
  product, version, build, "Licensed to <agency>", server, made by, support
  email, phone, website, copyright, and a "Copy details for support" button.
- **Not** printed on the customer's invoices or other documents.
- Fixed at build time so a customer cannot remove or replace it.

## 5. Sign-in screen: three layouts to choose from

All three follow Home's rules: white where you type, neutral greys around it,
the accent blue for the one main button, the status line at the foot, and the
agency's logo, name and tagline.

| Layout | Description | Suits |
| --- | --- | --- |
| **A. Brand panel + form** | A large dark panel on the left with the logo, name and tagline; the form on the right | The most "branded"; the common pattern on web products |
| **B. Home's frame, one card** *(chosen 2026-10-03)* | The dark bar at the top carries the logo and name and **becomes the menu bar after sign-in**, so nothing jumps; one plain card in the middle | Closest to Home, Tally and Business Central; the quietest |
| **C. Home's frame, pick who you are** | As B, plus tiles of the people who signed in on this PC; a person clicks their name and types only the password; "Someone else" gives the full form | Shared billing-counter PCs |

**In every layout the product identifies itself** (owner, 2026-10-03): the
product's mark -- product logo, product name, "by <company>" and the tagline --
sits under the sign-in form, and the window title reads "<product> - Sign in",
so anyone who sees the screen can tell which product it is and whose. The
agency's branding stays the larger, upper element. Where the mark sits is offered three
ways (a separate badge under the form was tried first and looked detached):

1. **In the sign-in card's own foot** *(recommended)* -- part of the form, as
   Microsoft's and Zoho's sign-in boxes carry their mark.
2. **At the right of the dark top bar**, opposite the agency.
3. **A night-blue product band** replacing the status line, in the Jugnix
   colours.

**Our support beside the form** (owner, 2026-10-03): a night-blue panel in the
space beside the sign-in card -- "Stuck? We'll light the way." -- with the
support phone (call or WhatsApp, with hours), email, help website, a "Copy
details for support" button (version, server, PC name) and a line that a
forgotten password is reset by the firm's administrator. Placeholders until
the company is registered. In layout C it is a third column.

In every layout: username or email, password with show/hide, remember
username, keep me signed in, Sign in on Enter, Forgot password, the server's
status and the version at the foot, Application Settings behind the gear, a
one-line error for a wrong password that does not say which half was wrong,
and a narrow-window form.

## 6. The wireframes

Open `dist\windows\Design\Branding wireframes.html` in a browser. It holds
only this subject, as six steps in the order a customer meets them:
1. Installer, 2. Sign in, 3. First-run setup, 4. Main app,
5. Settings > Branding, 6. Help > About. A box at the top lists what is still open. Switches show the agency's branding given or not, our product as a
placeholder or as Jugnix Trade, the sign-in layout (A, B, C) and the product
fields at install (locked or editable).

Screenshots of the main states are in
`dist\windows\Design\Branding wireframes - screenshots\`. Earlier versions
(views 8 and 9 of the phase 2 wireframes, the 09-28 review PDF and the 09-29
and 10-03 screenshot sets) are in `dist\windows\Design\_old (superseded)\`.

## 7. For the owner to decide or supply

1. ~~Sign-in layout~~ -- **decided 2026-10-03: B** (Home's frame, one card),
   with our support panel beside it, and the product mark in the card's foot.
1a. ~~Main app header~~ -- **decided 2026-10-03: option 1**: the agency's logo,
   name and tagline in the window's own title bar, then the selected firm's
   name (nothing when no firm is selected); the menu bar starts with Home and
   keeps the firm switcher; our product at the right of the status line.
2. ~~Product name and logo at install~~ -- **decided 2026-10-03: locked**; the
   installer wireframe is approved. Our company name, logo, tagline and
   product name are changed by us through an installer or update installer,
   never hard-coded.
2a. ~~First-run setup~~ -- **approved 2026-10-03**.
3. **Our company's details** for Help > About: support email, phone, website
   (placeholders until the company is registered).
4. **The logo set as vector files**, including the product icon (`.ico`) for
   the window and taskbar (backlog §47), once a designer redraws it.

## 8. What is built

Built in the order U2, U3+U4, U6, U5+U7, U1, one PR each (owner, 2026-10-04:
S2 showcase sign-in, keep "Agency Platform", support details blank, first-run
step 1 only; U8 Help > About stays parked).

### 8.1 Foundation (U2 and the server's record)

- **The agency's record** is `agency_branding` in the platform store
  (`backend/app/branding`, migration `20261004_0300`): name, tagline, accent
  colour and the logo image itself, so every PC reads the same logo from the
  server. One live row per installation, held by the unique index
  `UQ_agency_branding_key_active` rather than by a read. No row means not yet
  given.
- **Endpoints**, all under `/api/v1/branding`, a platform path:

  | Route | Who | Does |
  | --- | --- | --- |
  | `GET /api/v1/branding` | anyone, signed out | `is_set`, name, tagline, colour, `has_logo`, `version` (also the `ETag`) |
  | `GET /api/v1/branding/logo` | anyone, signed out | the image, `image/png` or `image/jpeg`; 404 when none |
  | `PUT /api/v1/branding` | `PLATFORM_SETTINGS` | replace name, tagline, colour; the first save creates the record |
  | `PUT /api/v1/branding/logo` | `PLATFORM_SETTINGS` | multipart `file`; PNG or JPG by its bytes, not its name; at most 1 MB |
  | `DELETE /api/v1/branding/logo` | `PLATFORM_SETTINGS` | remove the logo; initials show instead |

  Every write honours `If-Match` and is audited in the platform trail; a
  logo change records its type and size, never the image. A logo needs the
  name to be given first. The square shape is not checked by the server --
  the screens fit the image into a square.
- **Our product's identity** comes only from `desktop/config/branding.json`,
  which the package builds and every installer or update installer replaces:
  product and company names, tagline, company and product logos, support
  phone, WhatsApp, hours, email and website (blank for now; an empty row is
  hidden), and the eight sign-in strengths for the S2 panel.

### 8.2 Sign-in (U3, U4, S2)

- **Phase 2 only**: `desktop/lib/phase2/sign_in_screen.dart` wraps the same
  `LoginScreen` form through its `layoutBuilder`, so every sign-in behaviour
  (Enter, show/hide, remember, lockout, caps lock, settings) is one
  implementation; phase 1 keeps its layout untouched.
- **Layout S2**: night-blue showcase on the left cycling the strengths from
  `branding.json` every 8 s, stopping for good once either field is typed
  in; previous/next and dots; no strengths, no carousel. Below 900 px the
  card stands alone.
- **Agency**: name, tagline and logo from `GET /api/v1/branding` (one call
  on opening) and `GET /api/v1/branding/logo` (only when `has_logo` and the
  cached copy is of another version). The last answer is cached per server
  in `agency_branding.json` and `agency_branding_logo.bin` under the app's
  storage root, so the next start shows it at once. Not set, or no answer:
  `branding.json`'s name and logo; no logo: the agency's initials.
- **Product**: window title "<product> - Sign in"; the product mark (logo,
  name, "by <company>", tagline) in the card's foot; the status line shows
  the server state, version and "Powered by <product>".
- **More help** (U4, folded to one line by the owner): support rows, each
  hidden while blank; "Your administrator resets a forgotten password"; and
  "Copy details for support" (product, version, server, computer name).
- Wireframe colours that are not design tokens (the gold glow) are not used.

### 8.3 Main app header (U6, option 1)

- The app keeps Windows' own title bar, which cannot hold a logo, so option 1
  is built in two halves: the **window title** reads "<agency> > <firm>"
  (the firm part only while one is selected), and the agency's **logo, name
  and tagline lead the existing menu strip**, before Home, with no added
  height. Then the selected firm as plain text; the firm switcher stays.
- Below 820 px only the logo shows; the tagline shows from 1280 px. Clicking
  the agency opens Home.
- **No added requests**: the header reads the copy sign-in cached
  (`agency_branding_cache.dart`), once per shell; fallback `branding.json`,
  then initials.
- **Status line, right end**: product logo (placeholder icon until one is
  packaged), "<product> <version> by <company>", a tooltip with the same.
  No About on click -- Help > About is parked (U8).
- Not built: the "PRACTICE" mark (no practice-firm feature exists) and the
  "Finish setting up" prompt (U5, next).

### 8.4 Installer page 3, Branding (U1)

- `packaging/AgencyPlatform.iss`: a **Branding** page after "This PC",
  shown on a **fresh server install only** (skipped for an app-only PC, an
  upgrade and a repair). Agency name, tagline and a logo file with Browse,
  all optional; a tagline or logo without a name is refused on Next, and a
  logo path that does not exist. Below them, read-only: "This product:
  <product>, by <company>", from the package.
- The values travel **by file, never on a command line**: Setup writes them
  as UTF-8 JSON to `{tmp}randing.json`, passes `-BrandingFile` to
  `server_setup.ps1`, which runs `agency-server set-branding --file` once the
  server answers `/health`, then deletes the file.
- `set-branding` (`app/branding/services/installer.py`) saves through the
  same service as Settings > Branding, so it is audited. **A branding problem
  never fails an install**: a refused logo is logged as a warning and the
  name is still saved; the administrator can give it later.

### 8.5 Branding form, Settings page and first-run (U5 step 1, U7)

- **One form**, `desktop/lib/phase2/agency_branding_form.dart`: name
  (required), tagline, logo (PNG/JPG, at most 1 MB, checked before sending),
  a live preview of the sign-in card and the header strip, and our product,
  company and logo read-only ("set by the installer; changed only by an
  update"). The accent colour is not asked; the stored one goes back
  unchanged. Save is `PUT /branding`, then `PUT` or `DELETE /branding/logo`
  only when the logo changed, each with the last answer's version as
  `If-Match`; a refusal stays inside the form with everything typed. The
  shell takes the answer (and the logo bytes held locally) into the cache
  and the header at once -- no read.
- **Settings > Platform > Agency > Branding** (`branding_page.dart`), offered
  on `PLATFORM_SETTINGS`; opening it is one `GET /branding` and, when the
  record has a logo, one `GET /branding/logo`.
- **First-run step 1 "Set up your agency"** (`first_run_agency_dialog.dart`):
  after sign-in, once per shell, for a holder of `PLATFORM_SETTINGS` (or a
  platform administrator) while the cached record is not set. It makes no
  request until Save. **Skip for now** is kept per user in the workspace
  state (`phase2.first_run`, `agency_skipped`); Home then shows a "Finish
  setting up" card until branding is set. Steps 2-4 and a prompt in the
  header strip are not built.
- **When this PC holds no copy** (the cache is empty, so the state is
  unknown rather than "not set"), the dialog first asks the server once and
  opens only if the record really is not set -- otherwise an empty form saved
  without a version would replace the agency's branding.

