# syntax=docker/dockerfile:1

# Both build arguments must match how the project is developed:
#   PYTHON_VERSION  the Python the test suite runs on
#   UV_VERSION      the uv that wrote uv.lock; there is no default, so a missing value fails the
#                   build at once ("invalid reference format"). Get it with: uv --version
ARG PYTHON_VERSION=3.14
ARG UV_VERSION

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv


# --- builder: resolve nothing, install exactly what uv.lock says -----------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

COPY --from=uv /uv /uvx /bin/

# UV_PYTHON_DOWNLOADS=never: use this image's Python, the same one the runtime stage has, so
# the virtualenv's interpreter path is valid after it is copied across.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
# --frozen: never re-resolve, fail if uv.lock is out of date. --no-dev: no test or lint tools.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


# --- runtime: the interpreter, the virtualenv and the code; no uv, no build tools ------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=unknown
ARG REVISION=unknown
LABEL org.opencontainers.image.title="cloud-native-fastapi-platform" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

# PYTHONUNBUFFERED: logs reach stdout immediately. PYTHONDONTWRITEBYTECODE: the root
# filesystem can be read-only (the virtualenv's bytecode was compiled at build time).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

# A fixed numeric UID, so an orchestrator can verify the container is not root.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
# Owned by root and not writable by the app user: the process cannot modify its own code.
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY worker ./worker

USER 10001:10001

EXPOSE 8000

# Liveness only: is the process answering? It deliberately does not check the database
# (/health/ready), so a database outage cannot make the container look dead. Kubernetes ignores
# HEALTHCHECK and uses its own probes. The worker serves no HTTP and disables this check.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]

# One uvicorn process per container: the Prometheus registry lives in process memory, so more
# workers in one container would make /metrics report only the process that answered. Scale by
# adding containers. Exec form, so uvicorn is PID 1 and receives SIGTERM for graceful shutdown.
# uvicorn's own access log is off: RequestIDMiddleware writes a richer one.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
