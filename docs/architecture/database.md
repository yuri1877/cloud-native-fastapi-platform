# Database layer

## Stack
PostgreSQL (Amazon Aurora PostgreSQL in AWS) via SQLAlchemy 2.x async + `asyncpg`, with Alembic migrations.

## Configuration
| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | none | Secret. Must use `postgresql+asyncpg://`. Required in staging/prod (startup fails fast if missing). |
| `DB_POOL_SIZE` | 5 | Persistent connections per process. |
| `DB_MAX_OVERFLOW` | 10 | Extra short-lived connections above the pool size. |
| `DB_POOL_TIMEOUT` | 30 | Seconds to wait for a free connection before erroring. |
| `DB_POOL_RECYCLE` | 1800 | Recycle connections after N seconds (guards against idle-connection cuts by proxies/failover). |
| `DB_ECHO` | false | Logs SQL; development only. |

`DATABASE_URL` is a `SecretStr` and validation errors hide input values, so credentials do not reach logs or error output.
In AWS the URL is injected at runtime from Secrets Manager (added with the Aurora/secrets phases); it is never committed.

## Connection management
- One `AsyncEngine` per process, created in `create_app()` (lazy: no connection is opened until first use) and disposed on shutdown.
- `pool_pre_ping` is enabled so connections dropped during an Aurora failover are replaced transparently.
- One `AsyncSession` per request via the `get_session` dependency. The **service layer owns commits**; an uncommitted session is rolled back on close.
- Capacity rule of thumb: `(pool_size + max_overflow) x processes x replicas` must stay below the Aurora instance's `max_connections`. Revisit when sizing EKS and Aurora (Phases 23-24).

## Readiness
`/health/ready` runs `SELECT 1` with a 2s timeout and returns `503 NOT_READY` on failure. `/health/live` never touches the database, so a database outage does not restart healthy pods.
When no `DATABASE_URL` is set (local development only) readiness reports `database: not_configured`.

## Migrations
- Constraint names follow a naming convention so migrations are deterministic.
- `migrations/env.py` reads `DATABASE_URL` from settings; no URL is stored in `alembic.ini`.
- A test compares the migrated schema to the ORM models to catch drift.

```bash
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic revision --autogenerate -m "describe change"   # review the result before committing
```

## Testing against a real database
Integration tests use `TEST_DATABASE_URL`, which must point at a dedicated database whose name ends in `_test` (tests create and drop tables). Without it, those tests are skipped.

```bash
docker run --name pg-test -d -p 5432:5432 -e POSTGRES_PASSWORD=change-me -e POSTGRES_DB=app_test postgres:16
export TEST_DATABASE_URL=postgresql+asyncpg://postgres:change-me@localhost:5432/app_test
uv run pytest
```
