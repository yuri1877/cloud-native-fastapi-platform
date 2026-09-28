# Contributing

## Local checks (must pass before a PR)

```bash
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest
```

Database-backed tests run when `TEST_DATABASE_URL` is set (database name must end in `_test`);
see `docs/architecture/database.md`.

## Rules

- Keep changes small and coherent; add or update tests with every change.
- Never commit secrets or `.env` files. Use `.env.example` for placeholders only.
- Significant architectural decisions require an ADR in `ADR/`.
- Follow `PROJECT_SPEC_FastAPI_v1.0.md`; explain any deviation in the PR description.
