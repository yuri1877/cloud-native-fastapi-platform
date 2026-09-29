# Cloud-Native FastAPI Platform

A production-grade, cloud-native API platform (FastAPI + AWS + Terraform + GitHub Actions),
built as a portfolio case study for Solutions Architect / Cloud DevOps roles.

> **Status:** work in progress. Phases 0-7 complete (bootstrap, skeleton, configuration, database layer, user & order domains, error handling).
> The full README (architecture, trade-offs, cost, reliability) is delivered in Phase 33.

See `PROJECT_SPEC_FastAPI_v1.0.md` for requirements and `CLAUDE_IMPLEMENTATION_PLAN.md`
for the phased delivery plan.

## Local development

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload
```

- Swagger UI: http://localhost:8000/docs (disabled when `APP_ENV=prod`)
- Liveness: http://localhost:8000/health/live
- Readiness: http://localhost:8000/health/ready

## Database

See `docs/architecture/database.md` for configuration, migrations (`uv run alembic upgrade head`) and running database-backed tests via `TEST_DATABASE_URL`.

## Checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest
```
