# Database Infrastructure

`app.core.database` is the reusable persistence boundary for the application.
It deliberately contains no business models or tables.

| File | Responsibility | Future consumers |
| --- | --- | --- |
| `config.py` | Selects PostgreSQL or MySQL and constructs validated connection settings. | Deployment configuration, engine factory, Alembic |
| `engine.py` | Creates pooled engines and application-scoped database managers. | Application factory, workers, CLI commands |
| `session.py` | Creates short-lived sessions and supplies a schema-translation extension point. | Request dependencies, unit of work, tenant support |
| `dependencies.py` | Exposes `get_db` for FastAPI request handlers. | API routers |
| `base.py` | Defines shared metadata and deterministic constraint naming. | Every ORM model and Alembic |
| `entity.py` and `mixins.py` | Compose UUIDs, timestamps, soft deletion, audit columns, and optimistic-concurrency versions. | All future business entities |
| `types.py` | Defines portable UUID, JSON, datetime, and decimal types. | ORM model columns |
| `repositories/base_repository.py` | Provides generic repository contracts and soft-delete-aware SQLAlchemy operations. | Entity-specific repositories |
| `unit_of_work.py` | Defines service-owned transaction boundaries. | Application services |

`DatabaseManager.sessions(schema=...)` is the future tenant-schema extension
point. It applies SQLAlchemy's `schema_translate_map` only when a schema is
provided; tenant resolution remains intentionally out of scope.

```text
FastAPI router -> get_db -> DatabaseManager -> SessionManager -> SQLAlchemy Engine
Application service -> SQLAlchemyUnitOfWork -> Session -> BaseRepository -> BaseEntity
Alembic -> Base.metadata -> future ORM entities
Settings -> DatabaseConfig -> EngineFactory -> PostgreSQL or MySQL
```

Each `BaseEntity` has `id`, `created_at`, `created_by`, `updated_at`,
`updated_by`, `version`, `is_deleted`, and `deleted_at` fields. Repositories
exclude soft-deleted rows unless explicitly asked to include them.
