# Users and roles: API check, round 1 (2026-10-16)

Driven over HTTP against the running backend (http://127.0.0.1:8000), on TEST01 and TEST02 only.
Cases: `docs/qa/03_USERS_AND_ROLES.md` (57 cases) and rule 3 ("the server agrees") of
`docs/qa/01_ROLES_AND_ACCESS.md`. Kept checks: `docs/qa/checks/users-roles/` (`python docs/qa/checks/run.py users-roles`).

**Tally: 76 scripts, 71 clean, 5 failing, 4 distinct findings** (one finding fails two scripts).

| Group | Scripts | Result |
| --- | --- | --- |
| TC-USER-001..009 | 9 | clean (TC-USER-009 fails on finding 4) |
| TC-LOOK-001..006 | 6 | clean |
| TC-HIRE-001..004 | 4 | 001 and 004 clean; 002 and 003 fail on finding 1 |
| TC-TMPL-001..003, 005..015 | 14 | clean |
| TC-RTIER-001..008 | 8 | clean |
| TC-ROLE-001..009 | 9 | clean (after case-text drift was allowed for, see below) |
| 03-S01..S05 screen checks, server half | 5 | clean |
| Rule 3, one script per job template (11 jobs) | 11 | clean |
| Probes `p_ur_*` | 10 | 8 clean; `p_ur_receipts_list` and `p_ur_stale_version` fail (findings 2, 3) |

Fixtures: two runs (`shared-member-roles`, `sales-executive`). Every other user, role and template is made by the
script itself under a fresh tag and removed in `finally` (users soft-deleted, roles and templates deleted); seeded system
roles, global templates and users the checks did not create were never written. Six scratch accounts of mine left by
exploration were soft-deleted at the end.

## Method notes

* "Allowed" in rule 3 is "not refused": a write is sent with an **empty body**. The permission is checked before the body is
  read, so a job that holds the code gets 422 and one that lacks it gets 403, and no record is ever created. 403 is asserted
  with the standard message "You do not have permission to perform this action."
* A user made with `force_password_change: true` (the default of `POST /users`, and what clone sets) gets 403 on every
  route until the password is changed. That is the designed gate (TC-HIRE-002), but the refusal text is the generic
  permission message. Checks that sign in as a made user create it with the flag off.
* Platform-tier users are made by the platform administrator; the firm administrator then applies the job, as the screen does.

## Findings

| # | Severity guess | Case / probe | Endpoint | Expected | Got | Where |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Medium | TC-HIRE-002, TC-HIRE-003 | `POST /api/v1/users/{id}/clone` as a firm admin, source holds any role | 201, same roles | **404 "User not found."**, nothing created. A source with no roles clones fine; the platform admin's clone of the same source works. | `backend/app/identity/services/identity_service.py:1126-1128` calls `_stage_set_user_roles(clone.id, ...)`, which re-reads the clone through `_get_user` (2029, 2971-3006) with the firm filter; the clone's `UserFirm` is added at 595-603 without a flush and a request session does not autoflush, so the clone is not yet a member of the firm. Add `self._session.flush()` after the `UserFirm` is added in `_stage_create_user`. The unit suite autoflushes, which is why it cannot see it. Router: `app/identity/api/router.py:1085`. |
| 2 | Medium | `p_ur_receipts_list` (found under TC-ROLE-007) | `GET /api/v1/receipts` (page size 20 or more) on TEST01 | 200 | **404 "Customer not found."** for any page that holds a receipt whose customer is no longer live. 4 of TEST01's 46 receipts do (pages of 5 that avoid them pass), so Sell > Receipts cannot open. | `backend/app/settlements/services/settlement_service.py:2976-3013` (`parties_of` filters `is_deleted` at 3001 and raises at 3011-3013 for the whole page). Either read soft-deleted parties for a settlement that already exists, or stop a customer being deleted while receipts reference it (`customer_service.py:497`); the data shows the second guard does not hold. Data dependent. |
| 3 | Low | `p_ur_stale_version` | `GET/PATCH /roles/{id}`, `/users/{id}`, `/user-templates/{id}` | an `ETag` (and a version on the body), a stale `If-Match` refused | none of the three publishes one, so a precondition is impossible; two administrators editing the same role last-write-wins, and a role edit changes every holder | `app/identity/api/router.py:1156-1194` (roles), `:577-618` (users), `:1017-1057` (templates); responses `app/identity/schemas/api.py:186` (UserResponse), `:252` (RoleResponse), `:320` (UserTemplateResponse) carry no `version`. Customers publish `ETag: "1"`. |
| 4 | Medium | TC-USER-009 | `POST /api/v1/refunds` as Counter Sales (CASHIER) | 403 (case: no Refunds for the till) | **422** (allowed): refunds are gated on `PAYMENT_CREATE`, which CASHIER holds, while the desktop catalogue gates the Refunds screen on `ACCOUNT_MANAGE`. The menu hides it; the server lets a cashier hand money back. | `backend/app/settlements/api/router.py:108-110` (`RefundCreateScope` is `PAYMENT_CREATE`). Decide which is intended; if the screen is right, gate the refund route on `ACCOUNT_MANAGE` (or a refund code). |

Nothing found that lets a person act beyond their roles by privilege escalation: see the clean probes below.

## What the clean probes established

* `p_ur_platform_role_grant`: a firm admin cannot grant PLATFORM_ADMIN, LICENSE_ADMIN or SYSTEM_AUDITOR in the firm tier,
  the global tier, or a template; nobody (firm admin or seller) can grant themselves a role.
* `p_ur_platform_code_grant`: every platform-only permission code is refused for a custom role and for a system role,
  singly and mixed with an allowed code (all or nothing).
* `p_ur_reserved_case`: reserved role codes in other case, padded, with a zero-width space, or newline are all refused for
  both administrators; no row was created.
* `p_ur_other_firm`: naming TEST02 in `X-Firm-ID` as a TEST01 admin is 403 for roles, users, templates, permissions.
* `p_ur_cross_firm_user`: every read and write on a TEST02-only user is 403/404 for a TEST01 admin, including password
  reset and restore.
* `p_ur_deactivated_user`: a deactivated or deleted user's old token stops working and sign-in is refused.
* `p_ur_page_size`: 101, 0, -1, `abc` and `page=0` are 422 on users, roles, templates, permissions, lookup and audit logs.
* `p_ur_missing_targets`: unknown firm or role ids are refused (404/422, never 500); a soft-deleted user is 404 for every
  write and nothing is written for them.

## Case-text corrections suggested (the cases are not edited here)

1. **TC-ROLE-001**: twelve system roles are listed as the firm's, but there are now **thirteen** (`BILL_COLLECTOR` was added,
   with a `bill-collector` job template). "Four platform roles" is **three** visible (`PLATFORM_ADMIN`, `LICENSE_ADMIN`,
   `SYSTEM_AUDITOR`): `SUPPORT_ADMIN` is in `HIDDEN_SYSTEM_ROLE_CODES` (`app/identity/system_seed.py:34`) and no list shows it.
2. **TC-ROLE-002**: "the picker offers 167 codes; the 22 platform codes are filtered out" is now **213 offered, 28 filtered**.
3. **TC-TMPL section intro** and 01 `Summary`: "Eleven are seeded" is now twelve (`bill-collector`). The eleven named still hold.
4. **TC-USER-004 step 3 (HTTP half)**: a firm admin giving roles to somebody in no firm gets **404 "User not found."**, not
   "Add the user to this firm..." (that sentence is the platform admin's answer, TC-RTIER-008 step 3). The desktop message is client-side.
5. **TC-USER-009**: add that Refunds is hidden by the screen only; see finding 4.
6. **TC-HIRE-001 steps 3-4**: the server also refuses a non-email address (422) and a short password with the policy reasons; both confirmed.
7. **TC-LOOK-005 step 3**: "a plain `?q=qa.test` returns 10" holds only while at least 10 matches exist; the check asserts "at most 10" and an empty page 2.

## Cases not driven (screen only)

* TC-USER-001, 002, 003, 005: menu, button, read-only subtitle, prefilled Firms chip (the server facts behind each are driven).
* TC-USER-004 step 3 form message; TC-HIRE-001 steps 1-3 (dialog text, per-box messages, red banner).
* TC-LOOK-007 (User-Firm Assignments tab is a tab-level `requiresPlatformAdmin`: screen only).
* TC-TMPL-004 (chips lock and clear when a job is named; Job template field absent on Edit), TC-TMPL-012 (Offered-to picker: the
  server fact, a blank means every firm and a named firm sticks, is driven).
* TC-ROLE-007 menu table (the server half is driven: view and create codes open exactly those routes).
* Everything in 01 rules 1 and 2 (menu offers, buttons) for all eleven jobs; rule 3 is driven for all eleven.
* Hire into a **soft-deleted firm**: needs a firm created and left behind (the registry keeps a deleted firm's code); an
  unknown firm id is driven instead (`p_ur_missing_targets`).

## Files

`docs/qa/checks/users-roles/`: `setup.py`, `_ur.py` (helpers, the `job_check` table), `_roles.py`, `tc_user_001..009`, `tc_user_s01..s05`,
`tc_look_001..006`, `tc_hire_001..004`, `tc_tmpl_*`, `tc_rtier_*`, `tc_role_*`, `tc_acc_<job>` (11), `p_ur_*` (10).
