"""Guards the quality gates themselves: the configuration and the script that runs them, so a
gate cannot be dropped or loosened by accident. CI runs the same script."""

import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
CHECK_SCRIPT = ROOT / "scripts/check.sh"
PRE_COMMIT = (ROOT / ".pre-commit-config.yaml").read_text()


def _script_commands() -> str:
    lines = CHECK_SCRIPT.read_text().splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def test_mypy_is_strict_and_covers_the_application_and_the_worker() -> None:
    mypy = PYPROJECT["tool"]["mypy"]
    assert mypy["strict"] is True
    assert mypy["files"] == ["app", "worker"]


def test_pytest_rejects_unregistered_markers_and_registers_the_layers() -> None:
    options = PYPROJECT["tool"]["pytest"]["ini_options"]
    assert "--strict-markers" in options["addopts"]
    registered = {marker.split(":")[0] for marker in options["markers"]}
    assert {"contract", "e2e"} <= registered


def test_ruff_keeps_the_security_rules_and_only_exempts_asserts_in_tests() -> None:
    lint = PYPROJECT["tool"]["ruff"]["lint"]
    assert "S" in lint["select"]
    for pattern, ignored in lint["per-file-ignores"].items():
        assert ignored == ["S101"], f"{pattern} ignores more than assert statements"
        assert "test" in pattern or "conftest" in pattern, pattern


def test_coverage_measures_branches_of_the_application_and_the_worker() -> None:
    run = PYPROJECT["tool"]["coverage"]["run"]
    assert run["branch"] is True
    assert set(run["source"]) == {"app", "worker"}


def test_the_check_script_runs_every_gate_in_order() -> None:
    commands = _script_commands()
    gates = ["uv lock --check", "ruff format --check", "ruff check", "mypy", "pytest"]
    positions = [commands.index(gate) for gate in gates]
    assert positions == sorted(positions)


def test_the_check_script_is_executable_and_stops_at_the_first_failure() -> None:
    assert os.access(CHECK_SCRIPT, os.X_OK), "run: chmod +x scripts/check.sh"
    assert "set -euo pipefail" in CHECK_SCRIPT.read_text()


def test_pre_commit_runs_the_projects_own_pinned_tools() -> None:
    assert "uv run ruff format" in PRE_COMMIT
    assert "uv run ruff check" in PRE_COMMIT
    assert "uv run mypy" in PRE_COMMIT
    assert "repo: https://" not in PRE_COMMIT, "hooks must not pull in unpinned third-party repos"
