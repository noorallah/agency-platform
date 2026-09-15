# Agency Platform

Enterprise ERP platform with a FastAPI backend and Flutter desktop client.

## Repository structure

| Path | Purpose |
| --- | --- |
| `backend` | FastAPI APIs, domain services, migrations, and backend tests |
| `desktop` | Flutter desktop application, workspace framework, and widget tests |
| `docs` | Cross-cutting architecture and platform documentation |

## Core documentation

### Product and architecture

- `ARCHITECTURE_REVIEW.md`
- `SYSTEM_INTEGRATION_TEST_REPORT.md`
- `PURCHASE_MANAGEMENT_ARCHITECTURE.md`
- `docs/MULTI_INDUSTRY_ERP_ARCHITECTURE.md`
- `docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md`

### Rules and the defects behind them

`CLAUDE.md` holds the imperative half of every rule this codebase enforces;
these hold the narrative half — which defect, on what date, found how. They were
split out on 2026-09-15 when `CLAUDE.md` outgrew a single context window.

- `docs/TENANCY_AND_STORES.md` — how a request finds a firm's data
- `docs/ACCESS_CONTROL_FRAMEWORK.md` — roles, permissions, memberships, hiring
- `docs/API_AND_PERSISTENCE_CONVENTIONS.md` — routers, schemas, concurrency, migrations
- `docs/PRICING_AND_PROMOTIONS.md` — discounts, price lists, promotions, loyalty
- `docs/LEDGER_POSTING_RULES.md` — what posts to the ledger, and at what value
- `docs/SALES_CHAIN_RULES.md` — the sales chain and what may be skipped
- `docs/COMMISSION_FRAMEWORK.md` — rules, ladders, scope and payouts
- `docs/CUSTOM_FIELDS_FRAMEWORK.md` — the attribute framework
- `docs/GEOGRAPHY_MASTERS.md` — the geography masters and the area picker
- `docs/DEMO_DATA.md` — what the seeders produce, and what building history exposes

### Desktop UX and design system

- `docs/DESIGN_SYSTEM.md` (enterprise baseline)
- `desktop/docs/DESIGN_SYSTEM.md` (UX-1 desktop implementation baseline)
- `desktop/docs/DESKTOP_FRAMEWORK.md`
- `desktop/docs/UX_GUIDELINES.md`
- `desktop/docs/COMPONENT_LIBRARY.md`
- `desktop/docs/ICON_GUIDELINES.md`
- `desktop/docs/COLOR_GUIDELINES.md`
- `desktop/docs/DESKTOP_STYLE_GUIDE.md`

## Quick start

- **Running the application: [`docs/RUNNING.md`](docs/RUNNING.md)** — clean
  checkout to a signed-in client, including the demo logins
- **New to the code: [`docs/LEARNING_PATH.md`](docs/LEARNING_PATH.md)** — a
  measured module-by-module reading order
- Backend reference: `backend/README.md`
- Desktop reference: `desktop/README.md`
