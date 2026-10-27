"""Guards the security scanning setup, so a scanner cannot be dropped, turned advisory or given
a blanket exemption by accident."""

import os
import re
import tomllib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/security.sh"
SCRIPT_TEXT = SCRIPT.read_text()
GITLEAKS = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
PIP_AUDIT_IGNORES = (ROOT / "scripts/pip-audit-ignores.txt").read_text().splitlines()
DEPENDABOT = (ROOT / ".github/dependabot.yml").read_text()
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())

SOURCE_DIRECTORIES = ("app", "worker", "tests", "migrations", "terraform", "docs", "scripts")


def _gitleaks_values(key: str) -> list[str]:
    return [value for allowlist in GITLEAKS["allowlists"] for value in allowlist.get(key, [])]


def test_the_script_is_executable_and_stops_at_the_first_failure() -> None:
    assert os.access(SCRIPT, os.X_OK), "run: chmod +x scripts/security.sh"
    assert "set -euo pipefail" in SCRIPT_TEXT


def test_every_scanner_fails_the_run_when_it_finds_something() -> None:
    assert SCRIPT_TEXT.count("--exit-code 1") == 2  # trivy config and trivy image
    assert "|| true" not in SCRIPT_TEXT, "a scanner's failure must not be swallowed"
    assert "--exit-code 0" not in SCRIPT_TEXT


def test_a_missing_tool_is_an_error_not_a_skip() -> None:
    assert re.search(r"exit 3", SCRIPT_TEXT)
    for tool in ("uv", "gitleaks", "trivy", "docker"):
        assert f"need {tool} " in SCRIPT_TEXT, f"{tool} is used but never checked for"


def test_dependency_scanning_covers_the_locked_runtime_set_strictly() -> None:
    assert "--frozen --no-dev --no-emit-project" in SCRIPT_TEXT
    assert "--strict" in SCRIPT_TEXT, "an unauditable dependency must fail the scan"
    dev = {entry.split(">")[0].split("[")[0] for entry in PYPROJECT["dependency-groups"]["dev"]}
    assert "pip-audit" in dev


def test_secret_scanning_covers_the_working_tree_and_the_history() -> None:
    assert "gitleaks dir" in SCRIPT_TEXT
    assert "gitleaks git" in SCRIPT_TEXT
    assert GITLEAKS["extend"]["useDefault"] is True


def test_gitleaks_never_exempts_a_source_directory() -> None:
    for path in _gitleaks_values("paths"):
        for directory in SOURCE_DIRECTORIES:
            assert f"{directory}/" not in path, f"{path} exempts {directory}/"


def test_gitleaks_exemptions_for_values_are_exact_fakes_not_patterns() -> None:
    regexes = _gitleaks_values("regexes")
    assert regexes
    for regex in regexes:
        assert not re.search(r"\.[*+]|\[\^|\\[wWsSdD][*+]", regex), f"{regex} is a pattern"
        re.compile(regex)


def test_accepted_vulnerabilities_need_a_reason_and_an_unexpired_date() -> None:
    entries = [
        line for line in PIP_AUDIT_IGNORES if line.strip() and not line.lstrip().startswith("#")
    ]
    for entry in entries:
        match = re.search(r"#.+until (\d{4}-\d{2}-\d{2})", entry)
        assert match, f"{entry!r} needs '# reason (until YYYY-MM-DD)'"
        assert date.fromisoformat(match.group(1)) >= date.today(), f"{entry!r} has expired"


def test_dependabot_watches_the_python_dependencies() -> None:
    assert 'package-ecosystem: "uv"' in DEPENDABOT
