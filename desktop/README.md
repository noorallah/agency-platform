# Agency Platform Desktop

Flutter Material 3 desktop client for Phase 5 administration. It only calls the
REST API; it never accesses the database.

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
`/api/v1/dashboard`.

The client uses the standard backend envelopes: `{ "data": ... }` for a single
resource and `{ "data": [], "pagination": { "total_records": 0 } }` for a
collection. Lists use `page`, `page_size`, and optional `search` query
parameters. Firm updates use PUT; user, role, and permission updates use PATCH.
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
| Cannot connect to API | Confirm the backend is running, then set `API_BASE_URL` to the backend's reachable address. |
| `401` after startup | Sign in again. The stored refresh token may be revoked after a password change or logout. |
| `403` on an administration screen | Sign in with the platform administrator and verify backend role/permission assignments. |
| A form reports validation errors | Match the field requirements shown by the screen or inspect the backend `/docs` schema. |
| Flutter command is unavailable | Install the Flutter SDK with desktop support and ensure `flutter` is on `PATH`. |

## Validation

```powershell
flutter analyze
flutter test
```
