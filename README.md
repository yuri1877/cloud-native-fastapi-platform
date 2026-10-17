# Cloud-Native FastAPI Platform

A production-grade, cloud-native API platform (FastAPI + AWS + Terraform + GitHub Actions),
built as a portfolio case study for Solutions Architect / Cloud DevOps roles.

> **Status:** work in progress. 
Phases 0-17 complete (bootstrap, skeleton, configuration, database layer, user & order domains, error handling, request correlation, authentication, authorization, event architecture, SQS integration, EventBridge integration, structured logging, metrics, tracing, containerisation).
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

## Docker

```bash
# once: add the compose settings to your .env (see .env.example)
echo "UV_VERSION=$(uv --version | awk '{print $2}')" >> .env
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" >> .env

docker compose up --build
curl -s http://localhost:8000/health/ready
```

See `docs/deployment/docker.md` for the image, the compose stack and its limits (notably: no local identity provider, so `/api/v1/*` returns 503 until OIDC settings are supplied).

## Checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest
```
