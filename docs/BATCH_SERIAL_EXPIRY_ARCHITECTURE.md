# Enterprise Batch, Lot, Serial & Expiry Management Architecture

## Phase 16B – Enterprise Traceability Framework

---

## Overview

Phase 16B introduces a complete enterprise-grade traceability layer above the Inventory Foundation (Phase 16A). It supports Batch, Lot, Serial Number, and Expiry tracking for multiple industries without redesigning any existing modules.

---

## Architecture

```
Product (products)
    ↓  [tracking flags: track_batch, track_lot, track_serial, track_expiry, ...]
Inventory (inventories)
    ↓
Batch / Lot (batches / lots)          ← NEW (Phase 16B)
    ↓
Serial Numbers (serial_numbers)       ← NEW (Phase 16B)
    ↓
Inventory Transactions (inventory_transactions)
  [+ optional batch_id / lot_id / serial_id FK]  ← EXTENDED
    ↓
Stock Ledger (stock_ledger_entries)
    ↓
Future: Purchase · Sales · Manufacturing · Returns · Warranty
```

---

## Database Design

### Table: `batches`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| firm_id | UUID FK → firms | Multi-tenant |
| batch_number | VARCHAR(100) | Unique per firm |
| supplier_batch | VARCHAR(100) | External reference |
| internal_batch | VARCHAR(100) | Internal reference |
| product_id | UUID FK → products | |
| warehouse_id | UUID FK → warehouses | |
| branch_id | UUID FK → branches | |
| storage_node_id | UUID FK → warehouse_storage_nodes | |
| vendor_id | UUID FK → vendors | Optional |
| manufacturing_date | DATE | |
| expiry_date | DATE | Required for medical/food |
| best_before_date | DATE | |
| quantity | DECIMAL | Total received |
| available_qty | DECIMAL | Available for use |
| reserved_qty | DECIMAL | Reserved for orders |
| blocked_qty | DECIMAL | Blocked / quarantine |
| damaged_qty | DECIMAL | Damaged stock |
| status | ENUM | available, reserved, blocked, quarantine, expired, damaged, recalled, returned, destroyed |
| remarks | TEXT | |
| created_by / updated_by | UUID | Audit |
| created_at / updated_at / deleted_at | TIMESTAMP | Soft delete |

### Table: `lots`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| firm_id | UUID FK → firms | |
| lot_number | VARCHAR(100) | Unique per firm |
| lot_type | ENUM | production, mixing, manufacturing, assembly |
| parent_lot_id | UUID FK → lots | Self-referential for lot hierarchy |
| product_id | UUID FK → products | |
| warehouse_id | UUID FK → warehouses | |
| quantity | DECIMAL | |
| available_qty | DECIMAL | |
| status | ENUM | open, closed, quarantine, recalled, destroyed |
| remarks | TEXT | |
| Audit columns | | |

### Table: `serial_numbers`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| firm_id | UUID FK → firms | |
| serial_number | VARCHAR(200) | Unique per firm |
| product_id | UUID FK → products | |
| warehouse_id | UUID FK → warehouses | |
| branch_id | UUID FK → branches | |
| inventory_id | UUID FK → inventories | |
| batch_id | UUID FK → batches | Optional link to batch |
| manufactured_date | DATE | |
| warranty_start | DATE | |
| warranty_end | DATE | |
| current_owner | VARCHAR(255) | Customer / department |
| asset_ref | VARCHAR(100) | Asset management reference |
| status | ENUM | available, reserved, sold, installed, returned, repaired, scrapped, lost |
| remarks | TEXT | |
| Audit columns | | |

### Extended: `inventory_transactions`

Three nullable FK columns added:

| Column | Type | Notes |
|---|---|---|
| batch_id | UUID FK → batches | Optional |
| lot_id | UUID FK → lots | Optional |
| serial_id | UUID FK → serial_numbers | Optional |

### Extended: `products`

Eleven boolean tracking flags added:

| Column | Default |
|---|---|
| track_batch | false |
| track_lot | false |
| track_serial | false |
| track_expiry | false |
| track_manufacturing_date | false |
| track_warranty | false |
| allow_negative_stock | false |
| require_batch_on_receipt | false |
| require_batch_on_issue | false |
| require_serial_on_receipt | false |
| require_serial_on_issue | false |

---

## REST APIs

Base: `/api/v1/batch-serial`

### Batch Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /batches | List batches (paginated, filterable) |
| POST | /batches | Create batch |
| GET | /batches/{id} | Get batch detail |
| PUT | /batches/{id} | Update batch |
| DELETE | /batches/{id} | Soft delete batch |
| GET | /batches/summary | Expiry/status summary |

### Lot Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /lots | List lots |
| POST | /lots | Create lot |
| GET | /lots/{id} | Get lot detail |
| PUT | /lots/{id} | Update lot |
| DELETE | /lots/{id} | Soft delete lot |

### Serial Number Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /serials | List serial numbers |
| POST | /serials | Create serial |
| GET | /serials/{id} | Get serial detail |
| PUT | /serials/{id} | Update serial |
| DELETE | /serials/{id} | Soft delete serial |

### Dashboard Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /expiry-dashboard | Expiry summary (today/7d/30d/expired/quarantine/recalled) |

### Query Parameters (batches / lots / serials)

- `firm_id` (required)
- `product_id`, `warehouse_id`, `branch_id`, `vendor_id`
- `status`
- `expiry_before`, `expiry_after` (batches)
- `search` — matches batch/lot/serial number
- `page`, `page_size`

---

## RBAC Permissions

```
BATCH_VIEW      — view batch list and details
BATCH_CREATE    — create new batches
BATCH_UPDATE    — edit batch details
BATCH_DELETE    — soft-delete batches
BATCH_RESTORE   — restore deleted batches
SERIAL_VIEW     — view serial numbers
SERIAL_CREATE   — create serial numbers
SERIAL_UPDATE   — update serial numbers
SERIAL_DELETE   — delete serial numbers
SERIAL_RESTORE  — restore deleted serial numbers
```

---

## Desktop UI

### Module Catalog Tabs (Inventory Module)

| Tab ID | Section | Description |
|---|---|---|
| `batches` | BatchSerialSection.batches | Batch Master list |
| `lots` | BatchSerialSection.lots | Lot Master list |
| `serials` | BatchSerialSection.serials | Serial Number list |
| `expiry-monitor` | BatchSerialSection.expiryMonitor | Expiry dashboard |

### BatchManagementPage Sections

**Batches tab**
- `EnterpriseDataGrid<BatchRecord>` — Batch#, Product, Qty, Expiry, Status, Warehouse
- `FilterPanel` — status, warehouse, product, expiry range
- `DetailsPanel` — full batch details including date fields, quantities
- Context actions: `view`, `edit`, `delete`
- `WorkspaceContextAction.edit` opens `_BatchFormDialog`

**Lots tab**
- `EnterpriseDataGrid<LotRecord>` — Lot#, Type, Product, Qty, Status
- `FilterPanel` — status, lot type
- `DetailsPanel` — lot fields, parent lot
- `_LotFormDialog`

**Serials tab**
- `EnterpriseDataGrid<SerialRecord>` — Serial#, Product, Status, Warranty End
- `FilterPanel` — status, product
- `DetailsPanel` — serial fields, warranty info
- `_SerialFormDialog`

**Expiry Monitor tab**
- `ExpiryDashboard` widget showing 6 metric cards:
  - Expired Today, Expire in 7 Days, Expire in 30 Days
  - Total Expired, Quarantine, Recalled

---

## Business Profile Integration

The framework is driven by Business Profile feature flags. No values are hardcoded.

| Profile | Batch | Lot | Serial | Expiry |
|---|---|---|---|---|
| Medical/Pharmacy | ✓ Required | Optional | Optional | ✓ Required |
| Food | ✓ Required | Optional | ✗ | ✓ Required |
| Electronics | Optional | ✗ | ✓ Required | ✗ |
| Manufacturing | ✓ | ✓ Required | Optional | ✗ |
| General Trading | Configurable | Configurable | Configurable | Configurable |

The `BusinessProfileFeatureFlag` and `ProductConfig` tables (Phase 10) control which fields are required/optional per profile.

---

## Inventory Integration

- `InventoryTransaction` now has optional FK columns: `batch_id`, `lot_id`, `serial_id`
- These are populated at receipt/issue time when the product tracking flags demand it
- Stock ledger entries remain unchanged — traceability is at the transaction layer

---

## Traceability Strategy

### Forward Trace (from Batch)
```
Batch → InventoryTransaction (receipt) → Inventory
     → Future: SalesLine (issue)
     → Future: ManufacturingOrder
     → Future: ReturnLine
```

### Backward Trace (from Serial)
```
SerialNumber → batch_id → BatchRecord → vendor_id → Vendor
           → inventory_id → Inventory → warehouse → Branch
           → Future: SalesLine → Customer
```

### Extension Points
Each of `batches`, `lots`, `serial_numbers`, and `inventory_transactions` has FK slots ready for:
- Purchase Order Line (`purchase_line_id`) — future Phase 17
- Sales Order Line (`sales_line_id`) — future Phase 18
- Manufacturing Order (`manufacturing_order_id`) — future Phase 20
- Quality Control Hold (`qc_hold_id`) — future

---

## Future Integrations

### Purchase Module (Phase 17)
- GRN will populate `batch_id` / `lot_id` / `serial_id` on `InventoryTransaction`
- Batch receives `vendor_id` automatically from GRN

### Sales Module (Phase 18)
- Issue transactions record batch/serial consumed
- Serial status transitions: `available → sold`

### Manufacturing (Phase 20)
- Lot hierarchy (`parent_lot_id`) supports mixing/blending traceability
- Manufacturing orders create both input (consumed) and output (produced) lot transactions

### Warranty Management (future)
- `SerialNumber.warranty_end` is the extension point
- Warranty claim module reads serial status and flips to `returned` / `repaired`

### FEFO / FIFO (future)
- Batch `expiry_date` + `available_qty` are the data foundation
- Allocation engine will query batches ordered by `expiry_date ASC` (FEFO)

---

## Import / Export

Existing platform import/export framework applies:

| Operation | Format | Endpoint |
|---|---|---|
| Batch Import | CSV / XLSX | POST `/api/v1/batch-serial/batches/import` (future) |
| Serial Import | CSV / XLSX | POST `/api/v1/batch-serial/serials/import` (future) |
| Batch Export | CSV / XLSX | GET `/api/v1/batch-serial/batches/export` (future) |
| Serial Export | CSV / XLSX | GET `/api/v1/batch-serial/serials/export` (future) |

Desktop Import Wizard (Phase 16A.1 pattern) can be reused directly for batch/serial bulk import.

---

## Migration

File: `backend/alembic/versions/20260801_0020_enterprise_batch_serial_expiry.py`

Operations (in order):
1. Create `batches` table
2. Create `lots` table
3. Create `serial_numbers` table
4. `ALTER TABLE products ADD COLUMN track_batch ...` (11 columns)
5. `ALTER TABLE inventory_transactions ADD COLUMN batch_id ...` (3 columns)

Down migration reverses all operations.

---

## Audit

All three new entities (`BatchRecord`, `LotRecord`, `SerialNumber`) extend `BaseEntity` which provides:
- `created_by`, `created_at`
- `updated_by`, `updated_at`
- `deleted_by`, `deleted_at` (soft delete)

Status transitions are recorded via the existing `record_audit` service.

---

## Test Coverage

### Backend (10 new unit tests)

- `test_batch_crud` — create/read/update/delete batch
- `test_batch_soft_delete` — soft delete leaves record with `deleted_at`
- `test_lot_crud` — create/read/update/delete lot
- `test_serial_crud` — create/read/update/delete serial
- `test_serial_soft_delete`
- `test_batch_summary` — aggregation by status
- `test_expiry_dashboard` — dashboard counters
- `test_batch_list_filtering` — status + warehouse filters
- `test_serial_status_transition` — available → sold
- `test_multi_firm_isolation` — batches are firm-scoped

### Desktop (4 new widget tests)

- `batch management page shows empty state for batches section`
- `batch management page renders batch grid when batches are returned`
- `serial management page shows empty state for serials section`
- `lot management page shows empty state for lots section`

---

## Known Issues / Technical Debt

1. **Import/Export endpoints** for batch and serial are not yet implemented — only the data model and framework hooks exist. Tracked for Phase 17+.
2. **Recall Workflow** is not implemented — `status = recalled` can be set manually via API but no automated notification/workflow exists.
3. **FEFO / FIFO allocation** is not implemented — batch data is ready but the allocation engine belongs to Purchase/Sales phases.
4. **QC Hold integration** — `blocked_qty` and `quarantine` status are data-model ready but no QC module enforces them yet.
5. **Lot hierarchy depth** — `parent_lot_id` supports one level of parent; deep multi-level lot trees may require recursive CTE queries (not yet implemented).
6. **Serial movement history** — current model records current status/owner but does not yet maintain a full movement log table. Extension point: `serial_movements` table in Phase 18.

---

## Breaking Changes

None. All existing APIs and tables are unchanged. New columns on `products` and `inventory_transactions` are nullable with `server_default=False` to avoid migration failures on populated databases.

---

_Phase 16B completed. Ready for Phase 17 (Purchase) integration._
