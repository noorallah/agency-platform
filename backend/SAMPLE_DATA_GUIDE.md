# Enterprise ERP Sample Dataset Guide

## Overview

`scripts/generate_sample_data.py` now seeds one coherent, fully-linked enterprise dataset for:

- development
- manual QA
- automated tests
- demos

The dataset is **idempotent** because each run resets generated data first, then recreates the same deterministic data graph.

## Seeded company

- **Company:** Navkar Consumer Distribution Private Limited (`NAVK_CPL`)
- **Country:** India
- **Branches:** Mumbai Head Office, Pune Sales Branch, Bengaluru Operations Branch
- **Warehouses:** Main Distribution Warehouse + Returns and QC Warehouse per branch

## Covered modules

- Users & RBAC
- Business Profiles
- Geography
- Branches & Warehouses
- Products
- UOM & Packaging
- Tax Framework
- Vendors
- Customers
- Territories & Routes
- Inventory (opening stock + ledger/transactions)
- Purchase Orders
- GRNs
- Purchase Invoices
- Purchase Returns
- Sales Orders
- Delivery Notes
- Sales Invoices
- Document framework timeline/lifecycle mirrors

## Business scenario coverage

The seeded data includes:

- document lifecycle states: `DRAFT`, `APPROVED`, `COMPLETED`, `CANCELLED`, `CLOSED`
- partial receipts and partial deliveries
- multiple purchase and sales invoices against the same source document
- completed purchase returns
- stock reservations and reservation release
- opening stock posted with inventory and stock ledger trails
- attachments, notes, purchase history, and document lifecycle events

## Run sequence

From `backend`:

```powershell
uv run python -m alembic upgrade head
uv run python scripts/generate_sample_data.py --yes
uv run python scripts/verify_sample_data.py
```

## Reset only

From `backend`:

```powershell
uv run python scripts/generate_sample_data.py reset --yes
```

## Recreate from scratch

From `backend`:

```powershell
uv run python scripts/generate_sample_data.py --yes
uv run python scripts/verify_sample_data.py
```

## Generated artifacts

Each reseed refreshes:

- `DEVELOPMENT_USERS.md`
- `DEVELOPMENT_DATA_SUMMARY.md`

All seeded user accounts use:

```text
Password@123
```

Includes a dedicated **firm-level full-access** user (role: `FIRM_ADMIN`) scoped to the single seeded firm:

- `firm.owner@navkar.consumer.distribution.private.limited.local`
