-- Identity and firm tables, one section each.
--
-- A companion to `check_backend_data.sql`, which asks *questions* ("does the
-- ledger hold together"). This one is arranged by **table**: what is in it,
-- with foreign keys resolved to the codes a person recognises rather than the
-- UUIDs they are stored as.
--
-- **Every table here lives in the `platform` schema and nowhere else.** That
-- is why a firm-owned service reading one raises `UndefinedTable`, and why
-- these queries name the schema explicitly instead of relying on
-- `search_path`.
--
-- Each section shows **live rows only** (`NOT is_deleted`), except section 10,
-- which shows deleted firms too and says so. Soft-deleted rows
-- still exist and still hold their unique keys' releases -- drop the filter to
-- see them, which is what to do when an email or a firm code is refused as
-- taken but appears in no listing.
--
-- Nothing here writes.


-- ============================================================
-- 0. How much of everything there is
-- ============================================================
-- The map. Run this first; a table with zero rows is worth explaining before
-- reading further into it.

SELECT 'users'               AS table_name, COUNT(*) AS live_rows FROM platform.users               WHERE NOT is_deleted
UNION ALL SELECT 'roles',               COUNT(*) FROM platform.roles               WHERE NOT is_deleted
UNION ALL SELECT 'permissions',         COUNT(*) FROM platform.permissions         WHERE NOT is_deleted
UNION ALL SELECT 'role_permissions',    COUNT(*) FROM platform.role_permissions    WHERE NOT is_deleted
UNION ALL SELECT 'user_roles',          COUNT(*) FROM platform.user_roles          WHERE NOT is_deleted
UNION ALL SELECT 'user_firms',          COUNT(*) FROM platform.user_firms          WHERE NOT is_deleted
UNION ALL SELECT 'platform_admins',     COUNT(*) FROM platform.platform_admins     WHERE NOT is_deleted
UNION ALL SELECT 'user_templates',      COUNT(*) FROM platform.user_templates      WHERE NOT is_deleted
UNION ALL SELECT 'user_template_roles', COUNT(*) FROM platform.user_template_roles WHERE NOT is_deleted
UNION ALL SELECT 'firms',               COUNT(*) FROM platform.firms               WHERE NOT is_deleted
UNION ALL SELECT 'firm_storage_mappings', COUNT(*) FROM platform.firm_storage_mappings WHERE NOT is_deleted
ORDER BY table_name;


-- ============================================================
-- 1. users
-- ============================================================
-- The account. `email` is unique **only among live rows**, so soft-deleting
-- somebody releases their address for re-onboarding -- filter `is_deleted` in
-- any lookup or you will find a ghost.
--
-- `authorization_version` invalidates every issued token when it moves, which
-- is how a role change takes effect without waiting for expiry.

SELECT email,
       full_name,
       is_active,
       force_password_change,
       failed_login_attempts,
       locked_until,
       last_login_at,
       authorization_version,
       employee_code,
       department,
       designation
FROM platform.users
WHERE NOT is_deleted
ORDER BY email;


-- ============================================================
-- 2. roles
-- ============================================================
-- `firm_id` says who **wrote** the role, which is a different question from
-- where somebody *holds* it (section 5). NULL is a platform-wide definition
-- every firm may use; a firm id is a role that firm wrote for itself.
--
-- `is_system` marks the sixteen seeded roles, which the API refuses to edit.

SELECT r.code,
       r.name,
       r.is_active,
       r.is_system,
       COALESCE(f.code, '(every firm)') AS written_by,
       COUNT(rp.id) FILTER (WHERE NOT rp.is_deleted) AS permissions
FROM platform.roles r
LEFT JOIN platform.firms f ON f.id = r.firm_id
LEFT JOIN platform.role_permissions rp ON rp.role_id = r.id
WHERE NOT r.is_deleted
GROUP BY r.code, r.name, r.is_active, r.is_system, written_by
ORDER BY permissions DESC, r.code;


-- ============================================================
-- 3. permissions
-- ============================================================
-- The capability catalogue, `DOMAIN_ACTION`. A code enforced by
-- `require_permission` and missing here has no row to attach to any role, so
-- the endpoint silently becomes platform-admin-only.
--
-- Grouped, because 189 rows is a listing nobody reads.

SELECT SPLIT_PART(code, '_', 1) AS domain,
       COUNT(*)                 AS codes,
       STRING_AGG(code, ', ' ORDER BY code) AS which
FROM platform.permissions
WHERE NOT is_deleted
GROUP BY domain
ORDER BY codes DESC, domain;


-- ============================================================
-- 4. role_permissions
-- ============================================================
-- What each role can do. One row per pair, unique on both columns.
-- Change the filter to read a different role.

SELECT r.code AS role_code,
       p.code AS permission_code
FROM platform.role_permissions rp
JOIN platform.roles r       ON r.id = rp.role_id
JOIN platform.permissions p ON p.id = rp.permission_id
WHERE NOT rp.is_deleted
  AND r.code = 'CASHIER'
ORDER BY p.code;


-- ============================================================
-- 5. user_roles
-- ============================================================
-- **The table this whole area turns on.** A grant carries a tier:
--
--   firm_id IS NULL   the global set -- applies in every firm the person
--                     belongs to, and every firm they are added to later.
--                     Written by a platform administrator only.
--   firm_id = <firm>  that firm alone. Written by a platform administrator
--                     naming it, or by that firm's own administrator.
--
-- Effective access in a firm is the **union** of the two. A firm
-- administrator adds to the global set and cannot subtract from it.

SELECT u.email,
       r.code AS role_code,
       CASE WHEN ur.firm_id IS NULL THEN '(every firm)' ELSE f.code END AS granted_in,
       ur.created_at
FROM platform.user_roles ur
JOIN platform.users u ON u.id = ur.user_id
JOIN platform.roles r ON r.id = ur.role_id
LEFT JOIN platform.firms f ON f.id = ur.firm_id
WHERE NOT ur.is_deleted AND NOT u.is_deleted
ORDER BY u.email, granted_in, r.code;


-- ============================================================
-- 6. user_firms
-- ============================================================
-- Membership, and the firm somebody lands in. `is_primary` is one flag across
-- every firm a person belongs to, held by a partial unique index -- which is
-- why a caller who can see only some of their memberships must not set it.
--
-- Being a member grants nothing on its own: without a role in section 5 the
-- person opens an empty application.

SELECT u.email,
       f.code AS firm_code,
       uf.is_primary,
       uf.is_active,
       COUNT(ur.id) FILTER (WHERE NOT ur.is_deleted) AS roles_in_this_firm
FROM platform.user_firms uf
JOIN platform.users u ON u.id = uf.user_id
JOIN platform.firms f ON f.id = uf.firm_id
LEFT JOIN platform.user_roles ur
       ON ur.user_id = uf.user_id AND ur.firm_id = uf.firm_id
WHERE NOT uf.is_deleted AND NOT u.is_deleted
GROUP BY u.email, f.code, uf.is_primary, uf.is_active
ORDER BY u.email, f.code;


-- ============================================================
-- 7. platform_admins
-- ============================================================
-- The designation, which **no role can spell** -- it comes from this row and
-- nowhere else. `scope` is `PLATFORM` (runs the platform, refused a firm's
-- books) or `ALL_FIRMS`.
--
-- Zero memberships is not a fault for `ALL_FIRMS`: `/me/firms` widens to every
-- active firm for them, so their switcher fills without any `user_firms` row.

SELECT u.email,
       pa.scope,
       u.is_active,
       COUNT(uf.id) FILTER (WHERE uf.is_active AND NOT uf.is_deleted) AS memberships
FROM platform.platform_admins pa
JOIN platform.users u ON u.id = pa.user_id
LEFT JOIN platform.user_firms uf ON uf.user_id = u.id
WHERE NOT pa.is_deleted AND NOT u.is_deleted
GROUP BY u.email, pa.scope, u.is_active
ORDER BY u.email;


-- ============================================================
-- 8. user_templates and user_template_roles
-- ============================================================
-- A named bundle of roles -- hiring by naming the job. `firm_id` NULL means
-- offered to every firm, which needs **two** partial unique indexes rather
-- than one: PostgreSQL treats NULLs as distinct, so a single key on
-- (firm_id, code) would let the platform hold ten templates called the same
-- thing.
--
-- Nothing on a user records which template they came from: applying one is an
-- ordinary role assignment, and a user edited afterwards is no longer
-- described by it.

SELECT t.code,
       t.name,
       COALESCE(f.code, '(every firm)') AS offered_to,
       t.is_active,
       t.is_system,
       STRING_AGG(r.code, ', ' ORDER BY r.code) AS roles
FROM platform.user_templates t
LEFT JOIN platform.firms f ON f.id = t.firm_id
LEFT JOIN platform.user_template_roles tr
       ON tr.template_id = t.id AND NOT tr.is_deleted
LEFT JOIN platform.roles r ON r.id = tr.role_id
WHERE NOT t.is_deleted
GROUP BY t.code, t.name, offered_to, t.is_active, t.is_system
ORDER BY offered_to, t.code;


-- ============================================================
-- 9. firms
-- ============================================================
-- `code`, `gst_number` and `pan_number` are unique **among live firms only**,
-- so a deleted firm releases them. `financial_year_start` is what the
-- accounting calendar and the TCS threshold read.

SELECT code,
       name,
       country,
       currency_code,
       financial_year_start,
       status,
       is_active,
       gst_number,
       pan_number
FROM platform.firms
WHERE NOT is_deleted
ORDER BY code;


-- ============================================================
-- 10. firm_storage_mappings
-- ============================================================
-- Where each firm's rows live. One row per firm.
--
-- `deployment_mode` is fixed at creation -- nothing migrates a firm's data
-- between stores, so the service refuses to change it. A `SHARED` firm
-- carries NULL names and resolves to the configured shared store; reading the
-- NULLs directly resolves to no schema at all, which is a mistake worth
-- knowing about before writing a script against this table.
--
-- `provisioned_at` NULL on a dedicated firm means it cannot serve requests
-- yet, and `provisioning_error` keeps the reason on the record.
--
-- **A soft-deleted firm keeps its mapping, deliberately**, which is why this
-- is the one section showing them -- `firm_deleted` says which. Two firms may
-- never share a database/schema pair *including* deleted ones, because their
-- data is still there, so a store that looks free may not be.

SELECT f.code AS firm_code,
       f.is_deleted AS firm_deleted,
       m.deployment_mode,
       m.database_type,
       COALESCE(m.database_name, '(shared)') AS database_name,
       COALESCE(m.schema_name, '(shared)')   AS schema_name,
       COALESCE(m.connection_profile, '(platform server)') AS connection_profile,
       m.provisioned_at,
       m.provisioning_error,
       m.is_active
FROM platform.firm_storage_mappings m
JOIN platform.firms f ON f.id = m.firm_id
WHERE NOT m.is_deleted
ORDER BY f.code;
