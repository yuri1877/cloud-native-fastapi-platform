# Quality tooling

`scripts/check.sh` runs every gate in order and stops at the first failure. CI runs the same
script (Phase 29), so a change that passes locally passes there. `scripts/check.sh --no-tests`
skips the tests for a quick static pass.

| Gate | Command | What it protects |
|---|---|---|
| Lock file | `uv lock --check` | `uv.lock` matches `pyproject.toml`. The Docker build installs with `--frozen`, so a stale lock would otherwise surface late, at image build. |
| Formatting | `uv run ruff format --check .` | One style, no formatting arguments in review. |
| Lint | `uv run ruff check .` | Bugs, unused code, import order and security smells (rules below). |
| Types | `uv run mypy` | Strict type checking of `app/` and `worker/`. |
| Tests | `uv run pytest --cov` | Behaviour, plus coverage of `app/` and `worker/`. |

## Ruff
Rules `E, F, I, UP, B, SIM, S`: pycodestyle and pyflakes, import sorting, pyupgrade, bugbear,
simplifications, and bandit-derived security rules. Line length 100, target Python 3.12.
`S101` (use of `assert`) is exempted only in test files, because assertions are how pytest works;
a test guards that no pattern ignores anything else. In application code an `assert` is stripped
under `python -O`, so conditions that matter raise real exceptions.

Candidates to add later, one category at a time so each lands with its fixes: `ASYNC` (blocking
calls in async code), `C4` (comprehensions), `PT` (pytest style), `RUF`, `PERF`.

## mypy
`strict = true` with the pydantic plugin, over `files = ["app", "worker"]`, so `uv run mypy`
needs no arguments. Third-party stubs (`boto3-stubs`, `mypy-boto3-events`) are dev dependencies.
**Not checked:** `tests/` (the test helpers and OpenTelemetry's optional attributes would need
annotating throughout) and `migrations/`.

## pytest
`--strict-markers` turns a mistyped marker into an error instead of a silently ignored one;
`--strict-config` does the same for the configuration; `-ra` prints why tests were skipped;
`xfail_strict` makes an unexpectedly passing `xfail` fail. Markers `contract` and `e2e` select
those layers (`docs/operations/testing.md`).

Tests that need PostgreSQL are skipped without `TEST_DATABASE_URL`, which lowers coverage
sharply. **Always measure coverage with the database available**, as CI will.

## Coverage
Branch coverage of `app/` and `worker/` (`[tool.coverage]` in `pyproject.toml`).
`concurrency = ["greenlet", "thread"]` is required: SQLAlchemy's async layer runs code in
greenlets, and without it the repositories and services are under-reported.

`fail_under` is a **floor**, set a little below the measured total so noise does not fail a
build. It only goes up. It is a safety net against tests being deleted or a large untested
change slipping in, not a target: a high number says nothing about test quality, which is what
the contract and end-to-end layers are for. Excluded from the count: `if TYPE_CHECKING:` blocks,
`raise NotImplementedError`, protocol stub bodies (`...`) and `if __name__ == "__main__":`.
Not excluded: `worker/main.py`, which is entrypoint glue with no test yet, so it shows as
uncovered rather than hidden.

## Pre-commit hooks
`uv run pre-commit install` once. On every commit: `ruff format`, `ruff check`, and
`uv lock --check` when `pyproject.toml` or `uv.lock` changed. On push: `mypy`. Tests are not
hooks (they need a database and take longer); run `scripts/check.sh` before opening a PR.

All hooks are `repo: local` and call `uv run`, so they use the versions pinned in `uv.lock`.
There are no third-party hook repositories whose revisions would also need pinning and updating.

## What is not here yet
- Dependency vulnerability scanning, secret scanning, SAST, image and Terraform scanning
  (Phase 20, each with a documented purpose).
- The CI workflow that calls `scripts/check.sh` (Phase 29).
- Type checking of tests; more ruff rule categories; complexity limits.

## Testing the gates
`tests/unit/test_quality_config.py` checks that mypy is strict and covers `worker/`, that pytest
rejects unregistered markers, that ruff keeps its security rules and exempts only `assert` in
tests, that coverage is branch coverage of both packages, that `scripts/check.sh` runs the gates
in order, is executable and stops at the first failure, and that the hooks use only the
project's own tools.
