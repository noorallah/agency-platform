# Logo, agency name and company name: findings for review

Prepared 2026-09-28 for the owner to review; **updated 2026-10-03** after the
owner asked for the agency's branding to be given during installation and for
placeholders for our own product and company. Nothing here is built yet; the
build items are backlog §71 (`docs/BACKLOG.md`), parked as B9 until the
Jugnix trademark is filed. The wireframes are
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
| **Our company** (the maker) and **our product** | Jugnix / Jugnix Trade, shown as `[Company name]` / `[Product name]` with a placeholder logo until the trademark is filed | Fixed in the installer package's branding file; **locked at install** (approved 2026-10-03) | Installer and Windows' Apps list as publisher; exe properties; "Powered by <product>" on sign-in; right end of the status line; Help > About |

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
| **B. Home's frame, one card** *(recommended)* | The dark bar at the top carries the logo and name and **becomes the menu bar after sign-in**, so nothing jumps; one plain card in the middle | Closest to Home, Tally and Business Central; the quietest |
| **C. Home's frame, pick who you are** | As B, plus tiles of the people who signed in on this PC; a person clicks their name and types only the password; "Someone else" gives the full form | Shared billing-counter PCs |

**In every layout the product identifies itself** (owner, 2026-10-03): the
product's mark -- product logo, product name, "by <company>" and the tagline --
sits under the sign-in form, and the window title reads "<product> - Sign in",
so anyone who sees the screen can tell which product it is and whose. The
agency's branding stays the larger, upper element.

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

1. **Sign-in layout:** A, B or C (B recommended).
2. ~~Product name and logo at install~~ -- **decided 2026-10-03: locked**; the
   installer wireframe is approved.
3. **Our company's details** for Help > About: support email, phone, website
   (placeholders until the company is registered).
4. **The logo set as vector files**, including the product icon (`.ico`) for
   the window and taskbar (backlog §47), once a designer redraws it.
