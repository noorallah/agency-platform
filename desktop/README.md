# Agency Platform Desktop

Flutter Material 3 desktop foundation for Phase 8. It only calls the
REST API; it never accesses the database.

The official desktop UX standards and reusable component contracts are:

- [`docs\DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md)
- [`docs\DESKTOP_FRAMEWORK.md`](docs/DESKTOP_FRAMEWORK.md)
- [`docs\UX_GUIDELINES.md`](docs/UX_GUIDELINES.md)
- [`docs\COMPONENT_LIBRARY.md`](docs/COMPONENT_LIBRARY.md)
- [`docs\DESKTOP_STYLE_GUIDE.md`](docs/DESKTOP_STYLE_GUIDE.md)
- [`docs\ICON_GUIDELINES.md`](docs/ICON_GUIDELINES.md)
- [`docs\COLOR_GUIDELINES.md`](docs/COLOR_GUIDELINES.md)
- [`docs\LOGIN_SCREEN_GUIDELINES.md`](docs/LOGIN_SCREEN_GUIDELINES.md)

The broader enterprise design baseline is also documented in
[`..\docs\DESIGN_SYSTEM.md`](../docs/DESIGN_SYSTEM.md).

## Prerequisites and local run

Install Flutter with Windows, Linux, or macOS desktop support. The repository
contains the Flutter application sources but not generated native runners. From
`desktop`, generate them once:

```powershell
flutter create --platforms=windows,linux,macos .
flutter pub get
flutter run -d windows --dart-define=API_BASE_URL=http://localhost:8000
```

For Windows builds that use secure credential-vault storage, enable Windows
Developer Mode so Flutter can create plugin symlinks:

```powershell
start ms-settings:developers
```

For Linux or macOS, replace `windows` with the appropriate device. If the API
runs on another machine, provide its reachable URL:

```powershell
flutter run -d windows --dart-define=API_BASE_URL=http://192.168.1.20:8000
```

## Branding and preferences

Release bundles include `config\branding.json` beside the executable. Change
that external file to update product, company, support, logo, splash, and login
color branding without recompiling; restart the application to load the new
branding. Theme selection changes immediately and is synchronized to the
authenticated user's backend preferences after sign-in.

Local desktop preferences are stored separately from the OS credential-vault
refresh token. They include remembered username, server history, cached theme,
and window state. Choosing **Remember me** stores only the refresh token in the
credential vault; passwords are never stored.

## Module workspaces

The desktop shell exposes only high-level modules. Each module uses the shared
workspace frame, toolbar, search panel, data grid, details panel, pagination,
and status bar from `lib\ui\workspace`. Administration and Masters provide
tabbed workspaces for the available APIs; tabs without backend support remain
clearly marked as coming soon. Future ERP modules extend the module catalog and
reuse these components rather than adding screens directly to navigation.

Management grids use a compact selection summary for quick reference and
standard status badges. New, View Details, and Edit open the shared large
workspace dialog, which supports create, read-only, and edit modes, section
tabs, internal form scrolling, Escape to close, and Ctrl+S to save. Future
entity forms should extend this framework instead of creating module-specific
dialogs.

Customer Management is the reference business module under **Masters**. It
reuses the desktop framework for firm-scoped search, filters, soft-delete and
restore actions, CSV export, row copy, keyboard shortcuts, and the five-tab
customer workspace dialog. Its backend and extension contract are documented
in [`docs\CUSTOMER_MANAGEMENT.md`](../docs/CUSTOMER_MANAGEMENT.md).

Purchase Management is now the reference transactional module under
**Purchases**. It reuses the same workspace foundation for dashboard cards,
search and filter panels, lifecycle actions, tabbed order editing, CSV/XLSX
import preview, CSV/XLSX export, history, and responsive desktop behavior. Its
desktop and backend integration contract is documented in
[`..\PURCHASE_MANAGEMENT_ARCHITECTURE.md`](../PURCHASE_MANAGEMENT_ARCHITECTURE.md).

Start the current backend separately from `..\backend`:

```powershell
Set-Location ..\backend
Copy-Item config\.env.example config\.env
uv sync --group dev
uv run python -m alembic upgrade head
uv run uvicorn app.main:app --reload
```

## API contract assumptions

`API_BASE_URL` defaults to `http://localhost:8000`. Endpoint paths are isolated
in `lib/core/api/api_client.dart`: `/api/v1/auth/{login,refresh,logout,
change-password}`, `/api/v1/{firms,users,roles,permissions}`, and
`/api/v1/dashboard`, plus `/api/v1/business-framework/*` for business profile
administration and runtime module/feature activation.
Authenticated firm context uses `/api/v1/me/firms` and persists the selected
firm through `/api/v1/me/preferences`; each protected request also carries the
active firm identifier for firm-scoped APIs. Remote server addresses must use
HTTPS; plain HTTP is accepted only for loopback development addresses.

Purchase Management consumes `/api/v1/purchases` for list, summary, create,
update, delete, restore, cancel, close, history, and import flows.

The client uses the standard backend envelopes: `{ "data": ... }` for a single
resource and `{ "data": [], "pagination": { "total_records": 0 } }` for a
collection. Lists use `page`, `page_size`, and optional `search` query
parameters. Firm updates use PUT; user, role, and permission updates use PATCH.
Customer operations use `/api/v1/customers` and send the active firm through
`X-Firm-ID`; addresses and contacts are saved with the parent customer.
Business profile configuration uses `/api/v1/business-framework` endpoints and
the desktop module menu also filters from `/api/v1/business-framework/active-modules`.
User roles, firms, and role permissions use their dedicated PUT assignment
endpoints. Login/refresh responses contain `access_token`, `refresh_token`, and
`must_change_password`.

Only the refresh token is persisted, through a replaceable local token-store
abstraction. The desktop default uses the operating system credential vault;
no password, credential, or API secret is written to the preferences file.

## Desktop workflow

1. Start the backend and open the desktop app.
2. Sign in as the bootstrap administrator documented in `..\backend\README.md`.
3. Complete the forced password change.
4. Create permissions, roles, firms, and users; then configure role and firm
   assignments.
5. Use the dashboard to verify visible resource counts.

The client sends all data through REST. It never connects to PostgreSQL.
Requests automatically attempt one refresh-token retry after a `401`.
Validation and authorization errors are shown in the relevant screen.

## Debugging

| Symptom | Resolution |
| --- | --- |
| Cannot connect to API | Confirm the backend is running, then configure an HTTPS URL; HTTP is allowed only for localhost development. |
| `401` after startup | Sign in again. The stored refresh token may be revoked after a password change or logout. |
| `403` on an administration screen | Verify platform authority or the selected firm's membership and scoped role/permission assignments. |
| A form reports validation errors | Match the field requirements shown by the screen or inspect the backend `/docs` schema. |
| Flutter command is unavailable | Install the Flutter SDK with desktop support and ensure `flutter` is on `PATH`. |

## Validation

```powershell
flutter analyze
flutter test
```
