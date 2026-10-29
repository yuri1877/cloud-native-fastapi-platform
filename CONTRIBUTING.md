# Contributing

## Setup
```bash
uv sync
uv run pre-commit install      # formats and lints on commit, type-checks on push
```

## Checks (must pass before a PR)
```bash
scripts/check.sh               # everything CI runs, in CI's order
scripts/check.sh --no-tests    # static checks only: seconds, no database needed
```
Fix formatting and most lint findings with `uv run ruff format . && uv run ruff check --fix .`.
What each gate is for, and how to run them one at a time, is in
`docs/operations/quality-tooling.md`.

Database-backed tests run when `TEST_DATABASE_URL` is set (the database name must end in
`_test`); see `docs/operations/testing.md` and `docs/deployment/docker.md`.

## Rules
- Keep changes small and coherent; add or update tests with every change.
- Never commit secrets or `.env` files. Use `.env.example` for placeholders only.
- Significant architectural decisions require an ADR in `ADR/`.
- Follow `PROJECT_SPEC_FastAPI_v1.0.md`; explain any deviation in the PR description.
- Do not lower the coverage floor, loosen the type checker or widen a lint exemption to get a
  change through. If a gate is wrong, change it in its own PR with the reasoning.
