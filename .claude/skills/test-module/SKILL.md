---
name: test-module
description: Verify one module end to end against the running backend at the lowest token cost - drive its docs/qa cases over HTTP with kept scripts, fix what is found, re-drive until a round finds nothing new in that module. Use when asked to "test module <name>", verify a module, run a module pass or round, or continue the module-by-module zero-defect pass.
---

# Testing a module

One module per invocation. The argument is the module: `inventory`, `finance`,
`compliance`, `masters`, `users-roles`, `firms-config`, `sign-in`, `territory`,
`cross-cutting` (buying, selling and pricing are done). Its cases are the
matching file in `docs/qa/` (`07_INVENTORY.md`, `12_FINANCE_AND_REPORTS.md`,
...). With no argument, read `module-pass-state` in memory and take the next one
in the order; if the owner asked to be told before a module starts, ask first.

These rules exist because the pricing pass took nine rounds, and most of the
cost was agents rewriting scripts, re-driving what was already proven, and
chasing findings in other modules.

## The seven rules

1. **Checks are kept scripts, not a fresh agent job.** Every case and every
   re-drive of a fix is a script under `docs/qa/checks/<module>/` (outside
   `backend/`, so the linters do not apply). One file per case or defect,
   named for it (`tc_inv_004.py`, `d_stk_18.py`), each exiting non-zero with one
   line saying expected against got. `docs/qa/checks/run.py <module>` runs them
   all and prints **only failures** and a one-line tally. A later round runs the
   runner; it never rewrites or hand-drives an earlier check. Shared helpers
   (sign-in, fixture firm, request wrapper) live once in
   `docs/qa/checks/common.py`. If the runner or helper is missing, build it
   first, starting from the last round's `h.py`.
2. **Stay inside the module.** A finding that belongs to another module is
   fixed now only if it is High (wrong money, wrong stock, wrong tax, data
   loss). Anything else is logged in `docs/DEFECTS.md` against its own module
   and left for that pass. The module closes on "a round found nothing new **in
   this module** and no High elsewhere".
3. **Sonnet drives, Opus fixes.** The test agent is `general-purpose` with
   `model: sonnet`; driving cases and comparing figures is mechanical. Fix
   agents stay on the default model. Desktop work goes to a Sonnet agent.
4. **One branch and one PR per area per round, never one per defect** (owner,
   2026-10-07). An area is a set of services that share files (returns and
   credits; offers and claims; units and quantities). Every defect of the round
   in that area, any severity, goes on the one branch as **one commit per
   defect** with its id in the subject, so a single fix can still be reverted
   and the register can cite it. The PR is merged with a merge commit, not
   squashed, to keep those commits. The area's test files run once, at the end,
   before the merge - not once per defect. All of a round's schema changes go
   in one migration per branch. One fix agent takes the round; a second runs
   at the same time only when its area shares no files with the first, or for
   desktop work. A round therefore ends in one to three PRs and one
   pull + migrate + restart.
5. **Short reports.** The check file `docs/qa/<MODULE>_API_CHECK_ROUND_<n>_<date>.md`
   holds the detail. What an agent sends back is at most 30 lines: a table of
   id, severity, one-line symptom, file:line; then PRs merged, migrations, what
   was not fixed. Say this in every agent brief.
6. **Small saved state.** `module-pass-state` in memory keeps only: module,
   round number, main head, migration head, what is running (agent ids), what
   is owed next, open decisions. At each milestone **replace** the module's
   section rather than appending to it. History goes to
   `module-pass-archive.md`, which is read only when something in it is needed.
7. **Depth by module.** Core (`inventory`, `finance`, `compliance`): all cases,
   probes around each fix, and one market comparison (Tally, Zoho Books,
   ERPNext, Marg, Busy) - build the gaps a distributor needs, list the rest in
   `docs/BACKLOG.md`. Light (the other six): the cases plus a handful of
   probes, no market comparison, expected to close in one or two rounds.

## Backend and screens together

A module is verified only when **both** layers are clean (owner, 2026-10-07:
"backend and UI together we need to test and confirm that module works").

- **API layer** - the kept scripts of rule 1. They carry the figures, the edge
  cases and the refusals, because that is where they are cheap.
- **Screen layer** - the real desktop app against the running backend, driven
  by Flutter's `integration_test` (flows under `desktop/integration_test/`,
  one file per module, run with
  `flutter test integration_test/<module>_flow_test.dart -d windows --dart-define=API_BASE_URL=http://127.0.0.1:8000`).
  Each flow walks a screen's main path the way a person would: open the list,
  New, fill, Save, reopen, change, Save again, then each lifecycle button, and
  reads the result back from the screen. Main paths only - no edge cases here.
  Use the phase 2 UI and a fixture firm made for the run.
- A backend fix that changes a request or a response carries its desktop change
  **on the same branch**, or says in the PR that none is needed. Never merge
  the server half alone and leave the screen for later.
- The screen flows run at round 1 (to find what the screens get wrong today)
  and again on the closing round. Between those, only the flows of screens a
  fix touched.
- One build of the Windows app at a time, nothing else compiling, and more
  than 3 GB of memory free; stop the other agent's test runs first.

`integration_test` was **not wired up** when this was written (the `run-app`
skill records that the desktop could not be clicked). If
`desktop/integration_test/` does not exist, building the harness and proving it
on one flow (sign in, raise a sales order, save, reopen) is the first job, ahead
of any module. If it cannot be made to work on this machine, say so plainly and
fall back to the payload contract check (each editor's saved payload validated
against the server's request schema) - and do not call the screens verified.

## A round

1. `gh run list --limit 3` once, and `gh pr list` - fix a red main and check
   nothing open already covers the work.
2. Backend at main's head, stores at the migration head, `/health` answering.
   After any merge: pull, **immediately** `migrate_all_stores.py --yes` if a
   migration landed, then restart (kill the listener on 8000,
   `schtasks /run /tn agency-backend-8000`). Never pull while a round is driving.
3. Round 1: the test agent writes a script per case in the module's `docs/qa`
   file plus probes, runs them, writes the check file. Later rounds: run
   `run.py <module>` first (free regression), then add scripts only for the
   last round's fixes and probes around them.
4. Triage the findings yourself: severity, which module owns each, decide open
   questions by industry standard and record the decision. Give ids from the
   register (`D-<AREA>-n`, next free number).
5. Fix agent per rule 4. Review and merge desktop PRs yourself.
6. Save state (rule 6). Repeat from step 2 until a round is clean.

## Closing the module

One docs PR: register rows in `docs/DEFECTS.md` (all of the module's edits in
this one PR, never spread across fix PRs), corrected case text, the check files
and `docs/qa/checks/<module>/`, any backlog section. Regenerate `docs/qa` and
the PDFs. Then stop, tell the owner the module is closed and what stays open,
and wait for their word before the next module.

## Standing limits

- At most two agents at once. At most six new fixture firms per round, reusing
  the earlier ones; watch free memory (the database fell over under 1 GB).
  Dropping fixture schemas is destructive: only on the owner's word.
- Never the full backend or desktop suite, and no extra CI run, without asking.
  Merge on targeted tests and say which files ran.
- Held for the owner: anything needing a contract, money, the CA's ruling,
  hardware, branding or licensing.
- "Verified" means both layers ran clean. If only the API layer ran, say
  "backend verified, screens not" - never just "verified".
