# Core Framework

The Core Framework contains transport- and domain-independent infrastructure
that every future module reuses. Business entities and ERP rules remain outside
this package.

| Component | Responsibility | Future use |
| --- | --- | --- |
| `responses` | Standard success, error, validation, and paginated API contracts. | Every API router |
| `error_codes` and `exceptions` | Stable failure vocabulary and transport-neutral expected failures. | Services, repositories, API handlers |
| `validation` | Common input and business-rule validation helpers. | Request schemas and application services |
| `pagination`, `filtering`, `sorting` | Typed collection-query contracts with safe input validation. | List APIs and repositories |
| `context` | Request-scoped trace, client, and future user/firm metadata. | Logging, auditing, future identity |
| `middleware` | Context lifecycle, structured request/response logging, timing, and security headers. | Every HTTP request |
| `security` | Argon2 password primitives, JWT issuance/validation, and reusable FastAPI authorization dependencies. | Identity and protected APIs |
| `database` | Engine/session ownership, shared entities, transaction boundaries, and generic repositories. | ORM-backed modules |
| `constants` | Shared protocol, date, timezone, and pagination values. | All layers |
| `utils` | Stateless UUID, date, string, collection, and JSON helpers. | All modules |
| `openapi` | API metadata and shared error response documentation. | Every router |

```text
Identity ─┐
Tenant ───┼──> Core Framework <── Platform
Business ─┘          │
                      ├── API contracts and error handling
                      ├── request context and middleware
                      ├── JWT, password, and authorization primitives
                      ├── database sessions and shared entities
                      ├── validation and query contracts
                      └── constants and utilities
```
