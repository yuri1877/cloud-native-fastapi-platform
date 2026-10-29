#!/usr/bin/env bash
# Every quality gate, in the order CI runs them; stops at the first failure.
#
#   scripts/check.sh               everything
#   scripts/check.sh --no-tests    static checks only (seconds, no database needed)
#
# Local runs and CI use this one script, so they cannot drift apart.
set -euo pipefail

cd "$(dirname "$0")/.."

run_tests=1
for argument in "$@"; do
  case "$argument" in
    --no-tests) run_tests=0 ;;
    *) echo "unknown option: $argument" >&2; exit 2 ;;
  esac
done

step() { printf '\n==> %s\n' "$1"; }

step "uv.lock matches pyproject.toml"
uv lock --check

step "formatting"
uv run --frozen ruff format --check .

step "lint"
uv run --frozen ruff check .

step "types"
uv run --frozen mypy

if [ "$run_tests" -eq 1 ]; then
  step "tests with coverage"
  uv run --frozen pytest --cov --cov-report=term-missing:skip-covered
fi

printf '\nAll checks passed.\n'
