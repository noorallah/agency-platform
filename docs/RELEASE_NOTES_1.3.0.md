# Agency Platform 1.3.0: release notes and test hand-over

Release 1.3.0 is the **agency's branding release**: the agency's own name,
tagline and logo on the sign-in screen and at the top of every screen, given
at install or after the first sign-in, and the product's own name shown
quietly beside them. It upgrades 1.1.x and 1.0.x in place and backs up the
database first.

**Read this first: the 1.2.0 installer was never built.** Its build was
stopped before it finished, so no tester received it. 1.3.0 is therefore the
first installer since 1.0.2, and it carries **everything in the 1.2.0 notes**
(`docs/RELEASE_NOTES_1.2.0.md`: the light menu, Settings > Set up and
Platform, favourites, My preferences and the whole Wave 1 to 3 backlog build)
as well as the branding below. Treat the 1.2.0 rows as part of this pass.

Built 2026-10-04 from `main`: the 1.2.0 content up to #1062 (and the 1.2.0
test book, #1063), plus the branding work #1066 to #1070 and the version
bump #1071. Each item was checked by its own tests; many of the cases were
written from the code and have not yet been driven by hand, which is what
this pass is for.

## How to test it: one pass, in this order

Each row names the screen. Do them on a copy of a firm, or on the demo firm.
**Menu paths use the new menu** described in the 1.2.0 notes: each top
drop-down shows daily work only and every other screen is behind **All <Area>
screens** at its foot. **Ctrl+K** finds any screen by name if you lose one.

**Start with the sanity check** (`docs/qa/SANITY_CHECK.md`, PDF *Sanity check* in the hand-over folder). If it fails, report that before anything below.

**Then the branding rows below**, in order: rows 1 to 3 need a **fresh server
install** on a spare PC (the Branding page appears only there), so do them
first or last, not in the middle. Rows 4 onwards use the installation you
already have. The cases are TC-ME-014 to TC-ME-018 in
`docs/qa/02_SIGN_IN_AND_ACCOUNTS.md`, and QA-BRD-01 to QA-BRD-24 in
`docs/QA_TEST_BOOK.md`; the installer rows are also in
`docs/INSTALLER_QA_CHECKLIST.md` (section F). **After that, the 1.2.0 rows**
(next section).

### The agency's branding

| # | What | Where | What to look for |
| --- | --- | --- | --- |
| 1 | **Branding page of the installer** | Setup, a fresh **server** install: the page after *This PC* | Agency name, Tagline and a Logo file with Browse, all optional; below them, read-only, *This product: Agency Platform, by* its company. A tagline or logo without a name is refused on Next; a logo path that does not exist is refused. Leave all blank and the install is unchanged. **The page does not appear** for an app-only PC, an upgrade or a repair |
| 2 | **A refused logo never fails the install** | The same page, a text file renamed `fake.png`, or a picture over 1 MB | The install completes, the name is saved, no logo is saved (initials show), and the install log (`C:\ProgramData\Agency Platform\logs\install`) holds a warning; the logo can be added later (row 9) |
| 3 | **Branding saved after the server starts** | After such an install: sign in as the platform administrator; Settings > Platform > Audit Logs (no firm) | No *Set up your agency* dialog if a name was given; the name shows on the sign-in screen and at the top; the audit trail holds `agency_branding.created` |
| 4 | **Sign-in screen with the agency** | The sign-in screen | The agency's logo (or initials), name and tagline above the form; a night-blue panel at the left cycling eight strengths about every 8 seconds, **stopping for good once you type** in either box; arrows and dots; below 900 px wide the panel goes and the card stands alone; the title bar reads **Agency Platform - Sign in** |
| 5 | **Product mark and status line** | Foot of the sign-in card; status line | *Agency Platform*, by its company and tagline in the card's foot; the status line shows the server state, version 1.3.0 and *Powered by Agency Platform* |
| 6 | **More help, Copy details for support** | Sign-in screen > More help | Support phone, WhatsApp, hours, email and website show only when filled; **they are blank in this release by design**, so none appears; *Forgot your password? Your administrator resets it.*; **Copy details for support** copies product, version, server and this PC's name (no password) |
| 7 | **Server not answering** | Stop the server, reopen the app | The sign-in screen still opens at once with the agency's name, tagline and logo from this PC's last visit (or Agency Platform's own on a PC that never had one); no error box |
| 8 | **First sign-in: Set up your agency** | Sign in as the platform administrator while branding is not set | A dialog with name, tagline, logo and a live preview; **Skip for now** closes it and Home shows a **Finish setting up** card until it is set; Save with a name closes it and the card goes; it is not shown to a firm administrator or anyone without platform settings rights, and does not reopen for a user who skipped |
| 9 | **Settings > Platform > Agency > Branding** | Settings (gear) > Platform > Agency > Branding | One form: name (required), tagline, logo (PNG or JPG, at most 1 MB), a preview of the sign-in card and the top of every screen, and our product, company and logo read-only; **no accent colour box**; Save shows *Saved.* and the header changes at once; **Remove logo** shows the initials; a text file renamed `.png` is refused (*The logo must be a PNG or JPG image.*), an over-size picture is refused naming its size; two PCs editing at once: the second save is refused with the somebody-else-saved message and keeps what was typed |
| 10 | **Branding in the audit trail** | Settings > Platform > Audit Logs, no firm chosen | `agency_branding.created`, `agency_branding.updated`, `agency_branding.logo_changed` (the type and size, never the image), each naming who; another PC sees the new branding at its next sign-in screen |
| 11 | **The header** | Left of the menu strip; the window's title bar | The agency's logo, name and tagline lead the strip before Home, then the firm's name as plain text (firm switcher unchanged); the title bar reads **<agency> > <firm>**, the agency alone when no firm is chosen; below 820 px only the logo shows, the tagline from 1280 px; clicking it opens Home; no extra height |
| 12 | **Product on the status line** | Right end of the status line | *Agency Platform 1.3.0 by* its company and a tooltip with the same; clicking does nothing |

## Carried from the 1.2.0 notes

Everything in `docs/RELEASE_NOTES_1.2.0.md` is part of this build, and **no
tester has yet seen it on an installer**: its 75 rows (the light menu,
Settings > Set up and Platform, favourites, My preferences, the bell, and the
selling, buying, stock, accounts and tax, masters and reports rows) are to be
tested in full from those notes, with their menu paths. Behind them are the
1.1.0 notes (`docs/RELEASE_NOTES_1.1.0.md`) and everything since the 1.0.2
installer, which is the last build testers received.

## Fixed since 1.2.0

- The sign-in screen, the header and the status line had no place for the
  agency's own name and logo; they have (backlog 71).
- A fresh install had no way to name the agency; the Branding page and
  Settings > Platform > Agency > Branding give it.

## Known limits and what is not in it

- **Help > About is not built** (clicking the product on the status line does
  nothing).
- **First-run is step 1 only** ("Set up your agency"); the later steps, and a
  prompt in the header strip, are not built. Home's *Finish setting up* card
  stands in for them.
- **The "PRACTICE" mark** is not built (there is no practice-firm feature).
- **Support details are blank by design**: no phone, WhatsApp, hours, email
  or website is shown on the sign-in screen until they are packaged.
- The accent colour is stored but not asked or applied; the product logo on
  the status line is a placeholder icon until one is packaged.
- The logo's shape is not checked by the server; the screens fit it into a
  square.
- Everything under *Known limits* in the 1.2.0 notes still holds: the 26Q FVU
  file, live e-invoice and e-way bill, real WhatsApp and SMS sends, payment
  links, rule 43 and licensing are not built; *Rows per page* is not offered.

**On every failure**: a screenshot, the newest file in
`C:\ProgramData\Agency Platform\logs\server`, and the version on the sign-in
screen (1.3.0).

## Upgrading

Setup backs up the database, then migrates every firm's store to the new
schema (revisions up to `20261004_0300`: everything in the 1.2.0 notes, then
the one new platform table, `agency_branding`). Nothing existing changes how
it prices or posts. The branding is **empty after an upgrade**: no Branding
page is shown on an upgrade, so the first platform administrator to sign in is
asked *Set up your agency* (or skips it, and Home keeps the *Finish setting
up* card until it is given). Until then the sign-in screen and header show
Agency Platform's own name.

The two changes from 1.2.0 apply to anyone coming from an earlier build:

- **Date format becomes dd-MM-yyyy**, because nobody could choose one before.
  Anyone can change it under My preferences.
- **Admin screens are under Settings > Platform.** The Admin area is gone from
  the bar, and the *Primary firm* menu entry is replaced by *Start in firm* in
  My preferences.

Set-up lists (Pricing, Territories & routes, Account structure, Party lists,
Item lists, Locations) have moved out of the drop-downs to Settings > Set up.
