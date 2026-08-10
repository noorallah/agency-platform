-- Queries for checking backend data by hand.
--
-- Read this line before running anything else: **firm-owned tables exist once
-- per store.** `platform` holds identity, RBAC and the firm registry; every
-- other table lives in `firm_shared`, in each dedicated schema, and inside each
-- dedicated database. A query that forgets this reports on one store and looks
-- like the whole truth -- the same trap `alembic upgrade head` carries.
--
-- Section 1 tells you which stores exist. For sections 2 onward, either set the
-- schema first:
--
--     SET search_path TO wholesale_hub;
--
-- or qualify each table. Dedicated-database firms need a separate connection;
-- `psql -d agency_electrolink` for the seeded ELECTROLINK firm.
--
-- Every section is independent. Nothing here writes.


-- ============================================================
-- 1. Tenancy layout: which firms exist and where their data is
-- ============================================================
-- Run against the platform schema. This is the map for everything below.

SELECT f.code,
       f.name,
       m.deployment_mode,
       COALESCE(m.database_name, '(shared)') AS database_name,
       COALESCE(m.schema_name, '(shared)')   AS schema_name,
       f.is_deleted
FROM platform.firms f
LEFT JOIN platform.firm_storage_mappings m
       ON m.firm_id = f.id AND m.is_active AND NOT m.is_deleted
ORDER BY f.code;

-- Users and the firms they can act in. A user with no rows here can still log
-- in but cannot open a firm-owned screen.
SELECT u.email,
       COUNT(uf.id) FILTER (WHERE uf.is_active) AS active_firms,
       STRING_AGG(f.code, ', ' ORDER BY f.code) FILTER (WHERE uf.is_active) AS firms
FROM platform.users u
LEFT JOIN platform.user_firms uf ON uf.user_id = u.id
LEFT JOIN platform.firms f ON f.id = uf.firm_id
WHERE NOT u.is_deleted
GROUP BY u.email
ORDER BY active_firms DESC, u.email;

-- Two firms must never share a database/schema pair. More than one row here is
-- a provisioning fault, and it includes soft-deleted firms on purpose: their
-- data is still there.
SELECT COALESCE(database_name, '(shared)') AS database_name,
       COALESCE(schema_name, '(shared)')   AS schema_name,
       COUNT(*)                            AS firms,
       STRING_AGG(f.code, ', ')            AS which
FROM platform.firm_storage_mappings m
JOIN platform.firms f ON f.id = m.firm_id
WHERE m.deployment_mode <> 'SHARED'
GROUP BY 1, 2
HAVING COUNT(*) > 1;


-- ============================================================
-- 2. What is in this store, and over what period
-- ============================================================
-- Run per store. In firm_shared this covers every SHARED firm at once, so add
-- `WHERE firm_id = '...'` when you care about one of them.

SELECT 'customers'         AS entity, COUNT(*) FROM customers        WHERE NOT is_deleted
UNION ALL SELECT 'vendors',           COUNT(*) FROM vendors          WHERE NOT is_deleted
UNION ALL SELECT 'products',          COUNT(*) FROM products         WHERE NOT is_deleted
UNION ALL SELECT 'purchase_orders',   COUNT(*) FROM purchase_orders  WHERE NOT is_deleted
UNION ALL SELECT 'goods_receipts',    COUNT(*) FROM goods_receipts   WHERE NOT is_deleted
UNION ALL SELECT 'sales_orders',      COUNT(*) FROM sales_orders     WHERE NOT is_deleted
UNION ALL SELECT 'delivery_notes',    COUNT(*) FROM delivery_notes   WHERE NOT is_deleted
UNION ALL SELECT 'sales_invoices',    COUNT(*) FROM sales_invoices   WHERE NOT is_deleted
UNION ALL SELECT 'journal_entries',   COUNT(*) FROM journal_entries  WHERE NOT is_deleted
ORDER BY 1;

-- Trading period per firm. A single month means the history generator has not
-- been run: `python scripts/seed_multi_firm_demo.py`.
SELECT firm_id,
       COUNT(*)               AS invoices,
       MIN(invoice_date)      AS first_invoice,
       MAX(invoice_date)      AS last_invoice,
       SUM(grand_total)       AS invoiced_value
FROM sales_invoices
WHERE NOT is_deleted
GROUP BY firm_id
ORDER BY firm_id;

-- Documents per financial year, which is what a year-on-year report reads.
SELECT firm_id,
       CASE WHEN invoice_date >= DATE '2026-04-01' THEN '2026-27'
            WHEN invoice_date >= DATE '2025-04-01' THEN '2025-26'
            WHEN invoice_date >= DATE '2024-04-01' THEN '2024-25'
            ELSE 'earlier' END AS financial_year,
       COUNT(*)                AS invoices,
       SUM(grand_total)        AS value
FROM sales_invoices
WHERE NOT is_deleted
GROUP BY 1, 2
ORDER BY 1, 2;


-- ============================================================
-- 3. Does the ledger hold together
-- ============================================================

-- Posted journals must balance in total.
SELECT COUNT(*)          AS posted_entries,
       SUM(total_debit)  AS debits,
       SUM(total_credit) AS credits,
       SUM(total_debit) = SUM(total_credit) AS balanced
FROM journal_entries
WHERE status = 'POSTED' AND NOT is_deleted;

-- And each entry's lines must produce its header. Any row returned here is a
-- defect: the header claims a total its own lines do not sum to. This was
-- possible until 2026-08-10, when the engine checked the balance on unrounded
-- sums but stored each leg rounded.
SELECT e.reference_number,
       e.total_debit,
       SUM(l.debit_amount)  AS line_debit,
       e.total_credit,
       SUM(l.credit_amount) AS line_credit
FROM journal_entries e
JOIN journal_lines l ON l.journal_entry_id = e.id
WHERE NOT e.is_deleted
GROUP BY e.id, e.reference_number, e.total_debit, e.total_credit
HAVING SUM(l.debit_amount) <> e.total_debit
    OR SUM(l.credit_amount) <> e.total_credit;

-- Trial balance for a period. Debits should equal credits.
SELECT a.code,
       a.name,
       a.account_type,
       b.opening_balance,
       b.period_debit,
       b.period_credit,
       b.closing_balance
FROM ledger_balances b
JOIN ledger_accounts a ON a.id = b.ledger_account_id
JOIN accounting_periods p ON p.id = b.accounting_period_id
WHERE p.code = 'P05'          -- pick your period
ORDER BY a.code;

-- A firm should have one financial year per trading year. Only one row here
-- when documents span several years means the calendar was never extended, and
-- posting into the older years would have been refused.
SELECT firm_id, code, starts_on, ends_on,
       (SELECT COUNT(*) FROM accounting_periods p
         WHERE p.financial_year_id = y.id) AS periods
FROM financial_years y
WHERE NOT is_deleted
ORDER BY firm_id, starts_on;


-- ============================================================
-- 4. Do the receivables agree with the invoices
-- ============================================================

-- What each customer owes, against what was invoiced to them. A small
-- difference is expected and correct: receivables are stored to the paisa
-- (NUMERIC(18,2)) while documents carry four decimals, so each invoice is
-- rounded as it is posted. A large difference is not.
SELECT c.code,
       c.display_name,
       c.current_outstanding,
       COALESCE(SUM(i.grand_total), 0)                       AS invoiced,
       c.current_outstanding - COALESCE(SUM(i.grand_total), 0) AS difference
FROM customers c
LEFT JOIN sales_invoices i
       ON i.customer_id = c.id AND i.status = 'APPROVED' AND NOT i.is_deleted
WHERE NOT c.is_deleted
GROUP BY c.id, c.code, c.display_name, c.current_outstanding
ORDER BY ABS(c.current_outstanding - COALESCE(SUM(i.grand_total), 0)) DESC;

-- The receivable ledger must replay to the balance it claims.
SELECT c.code,
       c.current_outstanding,
       (SELECT t.outstanding_after
          FROM customer_receivable_transactions t
         WHERE t.customer_id = c.id AND NOT t.is_deleted
         ORDER BY t.created_at DESC, t.id DESC
         LIMIT 1) AS last_running_balance
FROM customers c
WHERE NOT c.is_deleted
ORDER BY c.code;

-- Customers over their credit limit. Zero means no limit set, not no credit.
SELECT code,
       display_name,
       credit_limit,
       current_outstanding,
       unapplied_advance_balance,
       ROUND(
         100 * (current_outstanding - unapplied_advance_balance)
             / NULLIF(credit_limit, 0), 1) AS percent_used
FROM customers
WHERE NOT is_deleted
  AND credit_limit > 0
  AND (current_outstanding - unapplied_advance_balance) > credit_limit * 0.8
ORDER BY percent_used DESC;


-- ============================================================
-- 5. Does the stock agree with its own ledger
-- ============================================================

SELECT p.code,
       p.name,
       v.quantity_on_hand,
       v.average_cost,
       v.total_value
FROM product_valuations v
JOIN products p ON p.id = v.product_id
WHERE NOT p.is_deleted
ORDER BY p.code;

-- Negative stock. Usually a defect, and always worth a look.
SELECT p.code, p.name, v.quantity_on_hand
FROM product_valuations v
JOIN products p ON p.id = v.product_id
WHERE v.quantity_on_hand < 0;

-- Movements by type. RESERVE/UNRESERVE/DISPATCH and the *_REVERSAL types are
-- written by the services; a type you do not recognise is worth asking about.
SELECT transaction_type, COUNT(*) AS movements, SUM(quantity) AS quantity
FROM inventory_transactions
GROUP BY transaction_type
ORDER BY 1;


-- ============================================================
-- 6. Document numbering
-- ============================================================

-- Duplicate numbers. Should always be empty -- a unique constraint enforces it
-- -- so a row here means the constraint is missing in this store.
SELECT po_number, COUNT(*) FROM purchase_orders  GROUP BY 1 HAVING COUNT(*) > 1
UNION ALL
SELECT invoice_number, COUNT(*) FROM sales_invoices GROUP BY 1 HAVING COUNT(*) > 1;

-- Counters per numbering scope. Each financial year keeps its own; before
-- 2026-08-10 a single counter was shared and back-dating a document reset it,
-- so the next current-year document collided.
SELECT r.code AS rule, s.scope_signature, s.next_sequence
FROM document_number_sequences s
JOIN document_numbering_rules r ON r.id = s.numbering_rule_id
WHERE NOT s.is_deleted
ORDER BY r.code, s.scope_signature;

-- The highest number issued per scope should be one below its counter.
SELECT SUBSTRING(po_number FROM '(\d{4}-\d{4})') AS financial_year,
       COUNT(*)        AS orders,
       MAX(po_number)  AS highest
FROM purchase_orders
WHERE NOT is_deleted
GROUP BY 1
ORDER BY 1;


-- ============================================================
-- 7. Business profile features
-- ============================================================

-- What this firm's profile enables. A write that fills a field belonging to a
-- feature absent from this list is refused with a 403 -- that is the gate
-- working, not a bug.
SELECT p.code AS profile, f.code AS feature, pf.is_enabled, f.is_implemented
FROM profile_features pf
JOIN business_features f ON f.id = pf.feature_id
JOIN business_profiles p ON p.id = pf.business_profile_id
WHERE NOT pf.is_deleted
ORDER BY p.code, f.code;

-- Features nothing implements. They stay listed as roadmap and cannot be
-- enabled; `is_enabled` must be false for all of them.
SELECT f.code, f.is_implemented,
       COUNT(*) FILTER (WHERE pf.is_enabled) AS profiles_claiming_it
FROM business_features f
LEFT JOIN profile_features pf ON pf.feature_id = f.id AND NOT pf.is_deleted
WHERE NOT f.is_implemented
GROUP BY f.code, f.is_implemented
ORDER BY f.code;


-- ============================================================
-- 8. Isolation between firms sharing a schema
-- ============================================================
-- Only meaningful in firm_shared, where several firms sit in one set of tables
-- separated by firm_id alone.

SELECT firm_id, COUNT(*) AS customers FROM customers WHERE NOT is_deleted GROUP BY 1;

-- Rows with no firm at all. Should be empty: every firm-owned row belongs to
-- exactly one firm.
SELECT 'customers' AS table_name, COUNT(*) FROM customers WHERE firm_id IS NULL
UNION ALL SELECT 'sales_invoices', COUNT(*) FROM sales_invoices WHERE firm_id IS NULL
UNION ALL SELECT 'products', COUNT(*) FROM products WHERE firm_id IS NULL;

-- A document must not reference a master belonging to a different firm.
SELECT i.invoice_number, i.firm_id AS invoice_firm, c.firm_id AS customer_firm
FROM sales_invoices i
JOIN customers c ON c.id = i.customer_id
WHERE i.firm_id <> c.firm_id;


-- ============================================================
-- 9. Audit trail
-- ============================================================
-- Per store, not central: a firm's history lives in its own database. No single
-- query answers "everything that happened" -- you have to visit each store.

SELECT entity_type, action, COUNT(*) AS events
FROM audit_logs
GROUP BY 1, 2
ORDER BY events DESC
LIMIT 20;

SELECT created_at, action, entity_type, actor_id
FROM audit_logs
ORDER BY created_at DESC
LIMIT 25;

-- Tables that grow without bound unless scripts/purge_retention.py runs.
SELECT 'tax_rule_execution_logs' AS table_name, COUNT(*), MIN(created_at) AS oldest
FROM tax_rule_execution_logs;
