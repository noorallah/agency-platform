# Logging

Both applications write levelled, rotating logs to a `logs` folder. The product
ships to machines nobody here can reach, so the log is often the only account of
what happened.

## Backend

Configured once at startup by `configure_logging` (`app/core/logging/configuration.py`)
and driven entirely by settings — nothing calls `basicConfig`.

| Setting | Default | Meaning |
|---|---|---|
| `AGENCY_LOG_LEVEL` | `INFO` | Root level |
| `AGENCY_LOG_DIRECTORY` | `logs` | Folder, created at startup |
| `AGENCY_LOG_FILE_NAME` | `application.log` | Live file |
| `AGENCY_LOG_MAX_BYTES` | `10485760` | Rotate at 10 MB |
| `AGENCY_LOG_BACKUP_COUNT` | `5` | Generations kept |
| `AGENCY_LOG_FILE_ENABLED` | `true` | Console only when false |

`RotatingFileHandler` keeps `application.log` plus `.1`…`.5`. Every line carries
`request_id`, injected by `RequestContextFilter` from the request context — the
same id returned to the client as `ApiResponse.requestId`, so a user's screenshot
joins straight to the server's account of that request.

Get a logger the normal way:

```python
logger = logging.getLogger(__name__)
logger.warning("Credit limit exceeded for %s", customer.code)
```

### Critical operations

An audit row answers *who changed this record*, and it is written inside the
transaction — so a failed posting rolls its own evidence back. The operation log
is the other half: written whichever way the operation ends.

```python
from app.core.logging import log_operation, operation

log_operation("sales_invoice.approve", document=invoice.number, firm=firm.code)

with operation("purchase.receive", firm=firm.code) as record:
    record["document"] = document.number     # added to the closing line
```

The context manager writes `started`, then `succeeded` with `duration_ms`, or
`failed` at `ERROR` with the exception type — and re-raises. It observes an
operation; it never changes whether it succeeds.

Keys are sorted so two runs of the same operation produce comparable lines, and
recognised secret keys (`password`, `refresh_token`, `token`, `secret`,
`api_key`, `authorization`, …) are redacted whatever a caller passes.

Use it for operations someone will be asked about later: posting, approving,
provisioning, imports, retention runs.

## Desktop

`AppLog` (`lib/core/logging/app_log.dart`) writes to
`%APPDATA%\.agency_platform\logs\agency_desktop.log` (`XDG_CONFIG_HOME`/`HOME`
elsewhere).

```dart
AppLog.debug('...');   AppLog.info('...');   AppLog.warn('...');
AppLog.error('...');   AppLog.recordError('Saving product', error, stack);
AppLog.operation('sales_invoice.approve', outcome: 'succeeded',
    details: {'document': 'INV-001'});
```

- **Level** defaults to `info` in release and `debug` in debug builds, and is set
  at build time: `--dart-define=LOG_LEVEL=debug`. An unrecognised value falls
  back to the build default rather than silencing the log by typo.
- **`operation` logs at `CRITICAL`**, so it survives a raised level. When someone
  asks whether the invoice posted, the answer has to be in the file even on a
  machine where debug and info are off.
- **Rotation** keeps `agency_desktop.log` plus `.1`…`.5` at 2 MB each. The
  previous implementation trimmed by discarding the file's older half, which
  threw away the beginning of the story exactly when it got long enough to
  matter.
- **Every line is written synchronously and flushed.** This exists because the
  client can disappear; an unflushed buffer dies with it.
- Timestamps are **UTC**, so a client log lines up with the backend's without a
  timezone guess.
- Writing never throws. Logging must not become the fault it exists to report.

### Crash reporting

`CrashReporter` (`lib/core/diagnostics/crash_reporter.dart`) sits on top:

- Writes a session marker at start, cleared only on a clean exit. If a launch
  finds the previous marker intact, the previous run was **killed** — this is the
  only way to observe a native crash, which a Dart handler cannot catch by
  definition.
- Groups failures by a stable FNV-1a fingerprint of error type plus normalised
  stack frames (`String.hashCode` is not stable across runs).
- Caps at 20 errors per session so a loop cannot flood anything.
- `DiagnosticsRedaction` strips JWTs, `Bearer` headers, passwords and tokens.

**Profile menu → Diagnostics report** (and the login screen's Settings dialog,
because a client that dies at startup never reaches the shell) builds one
plain-text report — header first with the previous-session verdict — with
**Save**, **Show in folder** and **Copy**. Plain text rather than an archive:
mail and ticket systems block attachments they cannot see inside.

## Crash reports reaching the server

`app/diagnostics` stores both halves in one `error_reports` table in the
**platform** schema. Unlike the audit trail — per firm store, for isolation and
per-firm restore — reports are telemetry for whoever maintains the product and
are useless scattered; `firm_id` is recorded as data, not used as routing.
`/api/v1/diagnostics` is registered as a platform path for that reason.

| Endpoint | Purpose | Gate |
|---|---|---|
| `POST /api/v1/diagnostics/client-errors` | desktop flushes its queue | authenticated |
| `GET /api/v1/diagnostics/errors` | faults grouped by fingerprint | `DIAGNOSTICS_VIEW` |
| `GET /api/v1/diagnostics/errors/{fingerprint}` | occurrences of one fault | `DIAGNOSTICS_VIEW` |

Ingest is authenticated rather than public: a public write endpoint needs its
own abuse protection, and the client queues on disk until it can sign in, so
nothing is lost. Firm and user are taken from the caller, never the payload — a
report cannot claim to come from somewhere it did not.

**Server failures record themselves.** `unhandled_exception_handler` persists a
`SERVER` row carrying the `request_id` the middleware generated — the same value
returned to the caller as `ApiResponse.requestId`, so a customer's screenshot
joins straight to the traceback. It opens its own platform session, because the
request's may be in a broken transaction, and swallows its own failures: this
runs while the request is already failing and must not make it worse.

**The desktop queues before it sends.** `ReportQueue` writes each report as JSON
under `%APPDATA%\.agency_platform\crash_queue\` and flushes after a successful
login. The failures most worth having happen before login, offline, or as the
process dies — none can finish an HTTP request. A refused upload leaves the
queue untouched; a corrupt entry is dropped so it cannot block the rest; the
queue is bounded at 50 and drops the oldest first.

Retention: `scripts/purge_retention.py --error-report-days` (default 90).

## Not yet built

No triage screen. Reports are read with SQL or through
`GET /api/v1/diagnostics/errors`; the grouped Administration view is still
outstanding, recorded in `MODULE_REVIEW_CHECKLIST.md` under Diagnostics.
