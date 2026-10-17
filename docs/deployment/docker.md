# Docker

## The image
`Dockerfile` has three stages: `uv` (just the uv binary), `builder` and `runtime`.

| Property | How |
|---|---|
| Exact dependencies | The builder runs `uv sync --frozen --no-dev`: it installs what `uv.lock` says, never re-resolves, and fails if the lock is out of date. |
| Small runtime | The runtime stage is `python:<version>-slim` plus the virtualenv and the code. It has no uv and no build tools. |
| Not root | Runs as numeric UID/GID `10001`, so an orchestrator's `runAsNonRoot` check can verify it. |
| Cannot rewrite itself | Code and virtualenv are owned by root; the app user cannot write to them. |
| Read-only filesystem | `PYTHONDONTWRITEBYTECODE=1`, and the virtualenv's bytecode is compiled at build time, so the root filesystem can be read-only. Compose does that. |
| Logs | `PYTHONUNBUFFERED=1`: everything goes to stdout/stderr immediately, as JSON (see `docs/operations/logging.md`). |
| No credentials | None in the image, the build arguments or the layers. Configuration arrives as environment variables. |
| One process | One uvicorn process per container (below). |
| Provenance | `VERSION` and `REVISION` build arguments become OCI labels. |

"Slim" is not "distroless": the base is still Debian with a shell, `apt` and `pip`. A distroless
runtime is a possible later hardening step.

### One process per container
The Prometheus registry lives in process memory (`docs/operations/metrics.md`). With several
uvicorn workers in one container, each scrape would reach an arbitrary one and the numbers would
be wrong. Scale by adding containers, not workers.

## Building
| Build argument | Default | Meaning |
|---|---|---|
| `PYTHON_VERSION` | `3.14` | Python for both stages. Keep it the version the tests run on. |
| `UV_VERSION` | none, required | The uv that wrote `uv.lock`: `uv --version`. No default, so a missing value fails immediately. |
| `VERSION`, `REVISION` | `unknown` | Written to the OCI labels. |

```
export UV_VERSION=$(uv --version | awk '{print $2}')
docker build --build-arg UV_VERSION="$UV_VERSION" \
             --build-arg REVISION="$(git rev-parse --short HEAD)" \
             -t cloud-native-fastapi-platform:dev .
```

### Determinism
Dependencies and the uv version are exact. The base image is pinned only by **tag**, and tags
move. For production builds pin by digest (`docker buildx imagetools inspect python:3.14-slim`,
then `FROM python:3.14-slim@sha256:...`) and let an update bot raise the pull requests. That
belongs with the CI pipeline (Phase 29) and is not done here.

## Running
```
# the API (needs DATABASE_URL etc. for anything beyond the health endpoints)
docker run --rm -p 127.0.0.1:8000:8000 cloud-native-fastapi-platform:dev

# the worker: same image, different command
docker run --rm -e SQS_QUEUE_URL=... cloud-native-fastapi-platform:dev python -m worker.main

# database migrations: same image again
docker run --rm -e DATABASE_URL=... cloud-native-fastapi-platform:dev alembic upgrade head
```
Migrations are a separate one-off step, never run by the API on startup: several replicas must
not race to migrate. In compose it is the `migrate` service; in Kubernetes it will be a Job.

## Health check strategy
- **The image's `HEALTHCHECK` is liveness only**: it calls `/health/live`, which never touches the
  database. A database outage must not make the container look dead and trigger restarts.
- **Readiness** (`/health/ready`, which checks the database) is for the orchestrator. In
  Kubernetes (Phase 24) the probes are liveness -> `/health/live`, readiness -> `/health/ready`.
  Kubernetes ignores `HEALTHCHECK`.
- **The worker serves no HTTP**, so compose disables the check for it. A process-level probe for
  it belongs with the Kubernetes work.

## Local stack: `docker-compose.yml`
| Service | Purpose |
|---|---|
| `db` | PostgreSQL 16. Creates the `app` database and, once, an `app_test` database for the integration tests. |
| `migrate` | One-off: `alembic upgrade head`, then exits. |
| `api` | The API on `127.0.0.1:8000`. Waits for `migrate` to succeed. |
| `worker` | Only with `--profile worker`. Needs a reachable SQS queue; AWS credentials are passed through from your shell, never written to a file. |

### First run
```
echo "UV_VERSION=$(uv --version | awk '{print $2}')" >> .env
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" >> .env   # hex is URL-safe
docker compose up --build
```
`.env` is git-ignored. Compose reads it for the `${...}` values only; the containers get their
environment from the compose file, not from `.env`, so the `localhost` `DATABASE_URL` you use
outside Docker does not leak in.

| Compose variable | Default | |
|---|---|---|
| `UV_VERSION` | required | see Building |
| `POSTGRES_PASSWORD` | required | URL-safe: it is embedded in `DATABASE_URL` |
| `POSTGRES_USER`, `POSTGRES_DB` | `app` | |
| `POSTGRES_PORT`, `API_PORT` | `5432`, `8000` | host ports; change them if something already uses them |
| `PYTHON_VERSION`, `LOG_LEVEL`, `AWS_REGION` | `3.14`, `INFO`, `eu-west-2` | |
| `SQS_QUEUE_URL` | empty | worker profile only; the API falls back to logging events |

### What is hardened
Ports are bound to loopback only. The app containers run with a read-only root filesystem
(`/tmp` is a tmpfs), all capabilities dropped and `no-new-privileges`. If something legitimately
needs to write, remove `read_only: true` to confirm, then give it a specific tmpfs. There is no
Redis because nothing uses it.

### Integration tests against it
```
export TEST_DATABASE_URL="postgresql+asyncpg://app:$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)@localhost:5432/app_test"
uv run pytest
```

### Calling the API locally: no identity provider
Every `/api/v1/*` route needs a bearer token (`docs/security/authentication.md`) and the stack
has no identity provider, so those routes return `503 AUTH_NOT_CONFIGURED`. Health, `/metrics`
and `/docs` work. To exercise the API, supply OIDC settings in a git-ignored
`docker-compose.override.yml`, which compose loads automatically:

```
services:
  api:
    environment:
      OIDC_ISSUER: https://your-tenant.example.com/
      OIDC_AUDIENCE: platform-api
      OIDC_JWKS_URL: https://your-tenant.example.com/.well-known/jwks.json
```

## Not done yet
- **Image scanning and secret scanning** (Phase 20) and **building and pushing in CI** (Phase 29).
- **Digest-pinned base images**, **SBOM** and **image signing**.
- **A local identity provider** for the compose stack.
- **Multi-architecture images.** Builds are for the host architecture.

## Troubleshooting
| Symptom | Cause and fix |
|---|---|
| `invalid reference format` at the first `FROM` | `UV_VERSION` is not set. |
| `uv sync` says the lockfile needs updating | `uv.lock` is stale or not committed: run `uv lock` and commit it. |
| A dependency tries to build from source and fails | No wheel for that Python version on Linux. Try `PYTHON_VERSION=3.13`. |
| `port is already allocated` | Set `POSTGRES_PORT` or `API_PORT` in `.env`. |
| `required variable ... is missing` | Set the named variable in `.env`. |

## Testing
`tests/unit/test_container_files.py` checks the Dockerfile, `.dockerignore` and compose file
without Docker: numeric non-root user, no floating tags, exec-form `CMD`, a health check, only
port 8000 exposed, no secret-like names, the lock file used with `--frozen`, loopback-only
ports, no literal passwords, hardening options present, no Redis. Building and running the image
is the real check.
