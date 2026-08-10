# Backlog

Work that is agreed but not started, with the decisions each one is waiting on.
Items move out of here when they are built, not when they are discussed.

Open feature-gating decisions live in `docs/MODULE_REVIEW_CHECKLIST.md` under
"three features deliberately left ungated" — they are questions rather than
tasks, so they stay there.

---

## 1. Make the remote UI work over the network

**Blocks: the installer.** Decide this first; whatever we choose, the installer
is what has to carry it.

The desktop client refuses plain HTTP to anything but `localhost` — see
`normalizeServerUrl` in
`desktop/lib/core/preferences/desktop_preferences_service.dart`. A client on
another machine therefore cannot reach `http://<lan-ip>:8000`, which is exactly
the deployment the product calls for.

Three ways out, in the order I would consider them:

1. **HTTPS on the backend with a self-signed certificate**, installed into the
   Windows trust store on every client by the installer. Keeps the guarantee,
   costs installer complexity.
2. **A reverse proxy** on the server machine terminating TLS. Same guarantee,
   another moving part to install and supervise on a low-specification box.
3. **Relax the rule for private-network addresses.** Cheapest, and it weakens
   the protection that stops credentials crossing the LAN in clear text. If we
   do this it should be a deliberate decision with its own tests, not a quiet
   edit.

Test cases are already written: `docs/MANUAL_UI_TEST_PLAN.md` §3.

## 2. Licence feature

Nothing implements licensing. A `LICENSE_MANAGE` permission, a `LICENSE_ADMIN`
role and a `license_error` error code exist and are unused — there is no model,
endpoint or screen.

Five questions decide what gets built, and each changes the tests:

1. What is licensed — the installation, the firm, the user, or a module?
2. What happens at expiry — read-only, blocked writes, or a grace period?
3. Phone home, or an offline key? Offline suits an on-premises Windows box with
   no guaranteed internet.
4. Who may see and enter a key — platform admin only, or a firm admin?
5. How is it stored so a determined user cannot simply edit it?

Whatever we choose, reads should stay possible after expiry so a firm can always
get its own data out.

Draft test cases: `docs/MANUAL_UI_TEST_PLAN.md` §10.

## 3. Single self-installing batch file

One Windows script that installs the prerequisites, migrates **every** schema,
starts the backend, and opens the UI. No Docker; target is a low-configuration
Windows machine.

Waiting on item 1 — the installer has to set up whatever transport we settle on,
including placing a certificate in the trust store if it comes to that.

Things it must get right, each of which has bitten this project already:

- **Migrate every store, not just `platform`.** `alembic upgrade head` advances
  one schema, chosen by `AGENCY_DATABASE_SCHEMA`. A firm store left behind is
  invisible until a query hits a missing column.
- **Enumerate the real targets** from `firms` and `firm_storage_mappings` rather
  than a hardcoded list.
- Refuse to start with the development JWT key or without a bootstrap admin
  password, the way the app already does.
- Be safe to run twice.

Draft test cases: `docs/MANUAL_UI_TEST_PLAN.md` §2.

---

## 4. A skill for resetting and regenerating demo data

`seed_multi_firm_demo.py` now seeds masters and two years of trading in one
command, and `generate_transaction_history.py` regenerates one firm's history
on its own. Wrapping the sequence in a skill would make it one instruction
rather than a command plus the four `alembic upgrade head` runs that have to
precede it, and would carry the traps with it -- migrate every store, enumerate
the targets from the registry, clear `AGENCY_DATABASE_*` afterwards.

Worth doing when the reset sequence stops changing.

## Also open

- **Desktop does not pre-hide feature-gated fields.** The backend refuses them
  (a 403 naming the feature), but the UI lets a user type a barcode into a firm
  that has no barcode feature and only fails on save. Decide whether that is
  acceptable or whether the desktop should read `/active-features` and hide
  them. `docs/MANUAL_UI_TEST_PLAN.md` §6.8.
- **Nothing calls `setBusinessProfileFeatures`.** The client method exists; no
  screen uses it, so features cannot be switched from the UI at all.
- **`tests/` still has about 40 ruff findings** — missing docstrings and long
  lines in older test files. `app/` is clean.
