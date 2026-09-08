-- Queries for checking user and firm administration data by hand.
--
-- Everything here lives in the **platform** schema: users, roles,
-- permissions, memberships, templates, preferences and the firm registry are
-- platform tables, and a firm's own store holds none of them. So unlike
-- `check_backend_data.sql` there is no per-store trap; one connection to the
-- platform database answers all of it. The one exception is section 9: a firm
-- administrator's staffing actions are audited on the platform trail with the
-- firm on `firm_id`, so that section reads the platform's `audit_logs`.
--
-- Two psql variables drive the filters. Set them once at the top, then run
-- any section:
--
--     \set user_email 'whole01.admin@agency.local'
--     \set firm_code  'WHOLE01'
--
-- In a client that is not psql, replace :'user_email' and :'firm_code' with
-- quoted literals. Every section is independent. Nothing here writes.

\set user_email 'whole01.admin@agency.local'
\set firm_code  'WHOLE01'


-- ============================================================
-- 1. The user: account state and designation
-- ============================================================
-- One row. `platform_scope` is NULL for anybody who is not a platform
-- administrator; ALL_FIRMS reaches every firm's books, PLATFORM runs the
-- platform and is refused a firm's books.

SELECT u.id,
       u.email,
       u.full_name,
       u.is_active,
       u.force_password_change,
       u.failed_login_attempts,
       u.locked_until,
       u.expires_at,
       u.last_login_at,
       u.authorization_version,
       u.employee_code,
       u.department,
       u.designation,
       pa.scope                               AS platform_scope,
       u.is_deleted,
       u.created_at,
       u.updated_at
FROM platform.users u
LEFT JOIN platform.platform_admins pa
       ON pa.user_id = u.id AND NOT pa.is_deleted
WHERE u.email = :'user_email';


-- ============================================================
-- 2. The user's firms: memberships, and which one is primary
-- ============================================================
-- Exactly one active row may be primary (UQ_user_firms_active_primary). A
-- sign-in lands on the primary; `default_firm_id` in section 6 decides only
-- for a person with no primary. A soft-deleted membership is shown so a
-- "removed then re-added" history is visible rather than hidden.

SELECT f.code,
       f.name,
       uf.is_primary,
       uf.is_active,
       uf.is_deleted,
       f.is_active                            AS firm_is_active,
       uf.created_at,
       uf.updated_at
FROM platform.user_firms uf
JOIN platform.users u ON u.id = uf.user_id
JOIN platform.firms f ON f.id = uf.firm_id
WHERE u.email = :'user_email'
ORDER BY uf.is_deleted, uf.is_primary DESC, f.code;


-- ============================================================
-- 3. The user's roles, by tier
-- ============================================================
-- `tier` is GLOBAL for a row with no firm (applies in every firm the person
-- belongs to, set on the user form by a platform administrator) and the
-- firm's code otherwise (set under Roles by firm). A role's own `firm_id`
-- says whether it is a platform-seeded role or one firm's custom role.

SELECT COALESCE(f.code, 'GLOBAL')            AS tier,
       r.code                                 AS role_code,
       r.name                                 AS role_name,
       r.is_system,
       r.is_active                            AS role_is_active,
       rf.code                                AS role_owned_by_firm,
       ur.is_deleted,
       ur.created_at
FROM platform.user_roles ur
JOIN platform.users u ON u.id = ur.user_id
JOIN platform.roles r ON r.id = ur.role_id
LEFT JOIN platform.firms f  ON f.id = ur.firm_id
LEFT JOIN platform.firms rf ON rf.id = r.firm_id
WHERE u.email = :'user_email'
  AND NOT ur.is_deleted
ORDER BY (ur.firm_id IS NOT NULL), f.code, r.code;


-- ============================================================
-- 4. What the user may actually do in one firm
-- ============================================================
-- The effective permission codes in :'firm_code': the union of the global
-- tier and that firm's tier, through the roles' permissions. A platform
-- administrator with ALL_FIRMS passes every check by designation and will
-- show few or no rows here -- that is the short-circuit, not a gap.

SELECT p.code                                 AS permission_code,
       STRING_AGG(DISTINCT r.code, ', ' ORDER BY r.code) AS through_roles
FROM platform.user_roles ur
JOIN platform.users u             ON u.id = ur.user_id
JOIN platform.roles r             ON r.id = ur.role_id AND r.is_active AND NOT r.is_deleted
JOIN platform.role_permissions rp ON rp.role_id = r.id AND NOT rp.is_deleted
JOIN platform.permissions p       ON p.id = rp.permission_id AND p.is_active AND NOT p.is_deleted
LEFT JOIN platform.firms f        ON f.id = ur.firm_id
WHERE u.email = :'user_email'
  AND NOT ur.is_deleted
  AND (ur.firm_id IS NULL OR f.code = :'firm_code')
GROUP BY p.code
ORDER BY p.code;


-- ============================================================
-- 5. The user's sign-ins and live sessions
-- ============================================================
-- Last twenty attempts, then the refresh tokens still usable. A token that
-- is neither expired nor revoked is a live session on some machine; a
-- password change or a role change revokes them all.

SELECT lh.created_at,
       lh.outcome,
       lh.failure_reason,
       lh.client_ip,
       LEFT(lh.user_agent, 60)                AS user_agent
FROM platform.login_history lh
WHERE lh.attempted_email = :'user_email'
ORDER BY lh.created_at DESC
LIMIT 20;

SELECT rt.created_at                          AS issued_at,
       rt.expires_at,
       rt.revoked_at,
       (rt.replaced_by_id IS NOT NULL)        AS rotated,
       (rt.revoked_at IS NULL AND rt.expires_at > NOW()) AS live
FROM platform.refresh_tokens rt
JOIN platform.users u ON u.id = rt.user_id
WHERE u.email = :'user_email'
ORDER BY rt.created_at DESC
LIMIT 20;


-- ============================================================
-- 6. The user's preferences
-- ============================================================
-- What the desktop reads at sign-in. `preferred_palette` exists since
-- 20260908_0132; `default_landing_page` is the last screen; `default_firm_id`
-- is the last firm switched into and decides the landing only when no
-- membership is primary.

SELECT up.preferences_version,
       up.preferred_palette,
       up.preferred_theme_mode,
       up.preferred_high_contrast,
       up.preferred_theme                     AS legacy_theme,
       f.code                                 AS default_firm,
       up.default_landing_page,
       up.rows_per_page,
       up.language,
       up.date_format,
       up.updated_at
FROM platform.user_preferences up
JOIN platform.users u ON u.id = up.user_id
LEFT JOIN platform.firms f ON f.id = up.default_firm_id
WHERE u.email = :'user_email';


-- ============================================================
-- 7. The firm: registry, storage and people
-- ============================================================
-- Where the firm's data lives, and who may work in it. A dedicated firm
-- with `provisioned_at` NULL serves no requests yet; `provisioning_error`
-- keeps the reason a build failed.

SELECT f.id,
       f.code,
       f.name,
       f.gst_number,
       f.pan_number,
       f.financial_year_start,
       f.is_active,
       f.is_deleted,
       m.deployment_mode,
       COALESCE(m.database_name, '(shared)') AS database_name,
       COALESCE(m.schema_name, '(shared)')   AS schema_name,
       COALESCE(m.connection_profile, '(platform server)') AS connection_profile,
       m.provisioned_at,
       m.provisioning_error
FROM platform.firms f
LEFT JOIN platform.firm_storage_mappings m
       ON m.firm_id = f.id AND m.is_active AND NOT m.is_deleted
WHERE f.code = :'firm_code';

-- Everybody in the firm, with their roles there and the global roles that
-- also apply there. `elsewhere` counts the other firms each person belongs
-- to: a person with any is a shared user whose profile only a platform
-- administrator may edit.
SELECT u.email,
       u.full_name,
       u.is_active,
       uf.is_primary,
       (SELECT STRING_AGG(r.code, ', ' ORDER BY r.code)
          FROM platform.user_roles ur
          JOIN platform.roles r ON r.id = ur.role_id
         WHERE ur.user_id = u.id AND ur.firm_id = f.id AND NOT ur.is_deleted) AS roles_in_firm,
       (SELECT STRING_AGG(r.code, ', ' ORDER BY r.code)
          FROM platform.user_roles ur
          JOIN platform.roles r ON r.id = ur.role_id
         WHERE ur.user_id = u.id AND ur.firm_id IS NULL AND NOT ur.is_deleted) AS global_roles,
       (SELECT COUNT(*)
          FROM platform.user_firms o
         WHERE o.user_id = u.id AND o.firm_id <> f.id
           AND o.is_active AND NOT o.is_deleted)                             AS elsewhere,
       (pa.id IS NOT NULL)                    AS platform_admin
FROM platform.firms f
JOIN platform.user_firms uf ON uf.firm_id = f.id AND uf.is_active AND NOT uf.is_deleted
JOIN platform.users u       ON u.id = uf.user_id AND NOT u.is_deleted
LEFT JOIN platform.platform_admins pa ON pa.user_id = u.id AND NOT pa.is_deleted
WHERE f.code = :'firm_code'
ORDER BY uf.is_primary DESC, u.email;


-- ============================================================
-- 8. The firm's own roles and templates
-- ============================================================
-- A firm may write its own roles and its own job templates; `firm_id` NULL
-- on either means platform-seeded and offered to every firm. Each role's
-- permission count is what an edit to it changes for everybody holding it
-- on their next token refresh -- roles are not versioned.

SELECT r.code,
       r.name,
       r.is_system,
       r.is_active,
       COALESCE(f.code, '(every firm)')      AS owned_by,
       (SELECT COUNT(*) FROM platform.role_permissions rp
         WHERE rp.role_id = r.id AND NOT rp.is_deleted) AS permissions,
       (SELECT COUNT(*) FROM platform.user_roles ur
         WHERE ur.role_id = r.id AND NOT ur.is_deleted)  AS holders
FROM platform.roles r
LEFT JOIN platform.firms f ON f.id = r.firm_id
WHERE NOT r.is_deleted
  AND (r.firm_id IS NULL OR f.code = :'firm_code')
ORDER BY (r.firm_id IS NOT NULL), r.code;

SELECT t.code,
       t.name,
       t.is_system,
       t.is_active,
       COALESCE(f.code, '(every firm)')      AS owned_by,
       STRING_AGG(r.code, ', ' ORDER BY r.code) AS roles
FROM platform.user_templates t
LEFT JOIN platform.firms f ON f.id = t.firm_id
LEFT JOIN platform.user_template_roles tr ON tr.template_id = t.id AND NOT tr.is_deleted
LEFT JOIN platform.roles r ON r.id = tr.role_id
WHERE NOT t.is_deleted
  AND (t.firm_id IS NULL OR f.code = :'firm_code')
GROUP BY t.id, t.code, t.name, t.is_system, t.is_active, f.code, t.firm_id
ORDER BY (t.firm_id IS NOT NULL), t.code;


-- ============================================================
-- 9. What administration did, on the platform trail
-- ============================================================
-- User administration runs on the platform session, so hiring, role edits,
-- promotions and primary-firm changes are recorded here with the firm on
-- `firm_id`. The firm's own Audit Logs screen merges this in on read. Last
-- fifty rows touching :'firm_code' or :'user_email'.

SELECT a.created_at,
       a.action,
       a.entity_type,
       a.entity_id,
       actor.email                            AS actor,
       f.code                                 AS firm
FROM platform.audit_logs a
LEFT JOIN platform.users actor ON actor.id = a.actor_id
LEFT JOIN platform.firms f     ON f.id = a.firm_id
LEFT JOIN platform.users subj  ON subj.id = a.entity_id AND a.entity_type = 'user'
WHERE f.code = :'firm_code'
   OR subj.email = :'user_email'
   OR actor.email = :'user_email'
ORDER BY a.created_at DESC
LIMIT 50;


-- ============================================================
-- 10. Things that should be true of every row
-- ============================================================
-- Each query lists violations, so an empty result is the healthy answer.

-- 10a. More than one active primary firm for one person. The partial unique
-- index holds this on PostgreSQL; a row here means it is missing.
SELECT u.email, COUNT(*) AS primaries
FROM platform.user_firms uf
JOIN platform.users u ON u.id = uf.user_id
WHERE uf.is_primary AND uf.is_active AND NOT uf.is_deleted
GROUP BY u.email
HAVING COUNT(*) > 1;

-- 10b. A firm-tier role in a firm the person is not an active member of:
-- reaches nobody, because the token is built per membership.
SELECT u.email, f.code AS firm, r.code AS role
FROM platform.user_roles ur
JOIN platform.users u ON u.id = ur.user_id
JOIN platform.roles r ON r.id = ur.role_id
JOIN platform.firms f ON f.id = ur.firm_id
LEFT JOIN platform.user_firms uf
       ON uf.user_id = ur.user_id AND uf.firm_id = ur.firm_id
      AND uf.is_active AND NOT uf.is_deleted
WHERE NOT ur.is_deleted AND ur.firm_id IS NOT NULL AND uf.id IS NULL
ORDER BY u.email, f.code;

-- 10c. A permission code the application enforces that no role grants.
-- Compare with `require_permission` calls; the seed test guards the other
-- direction (every enforced code exists).
SELECT p.code
FROM platform.permissions p
LEFT JOIN platform.role_permissions rp ON rp.permission_id = p.id AND NOT rp.is_deleted
WHERE NOT p.is_deleted AND p.is_active
GROUP BY p.code
HAVING COUNT(rp.id) = 0
ORDER BY p.code;

-- 10d. An active user with no firm and no platform designation: can sign in
-- and reach nothing. Allowed, but worth knowing about.
SELECT u.email, u.full_name, u.created_at
FROM platform.users u
LEFT JOIN platform.user_firms uf
       ON uf.user_id = u.id AND uf.is_active AND NOT uf.is_deleted
LEFT JOIN platform.platform_admins pa ON pa.user_id = u.id AND NOT pa.is_deleted
WHERE NOT u.is_deleted AND u.is_active AND uf.id IS NULL AND pa.id IS NULL
ORDER BY u.email;

-- 10e. A role code that is not uppercase. Role codes are uppercase, and the
-- platform designation used to be spelled as the lowercase `platform_admin`
-- inside the roles claim -- so a lowercase code is how a role could once
-- impersonate the designation. The service refuses one; a row here was
-- written some other way. The seeded `PLATFORM_ADMIN` role is uppercase and
-- legitimate, which is why this does not compare case-insensitively.
SELECT r.code, r.name, r.created_at
FROM platform.roles r
WHERE NOT r.is_deleted
  AND r.code <> UPPER(r.code)
ORDER BY r.code;
