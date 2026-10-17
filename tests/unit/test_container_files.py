"""Static checks on the container files, so the properties the spec asks for (non-root, no
secrets, no floating tags, exec-form CMD, a health check) cannot regress unnoticed.

They need no Docker. Building and running the image is the real check; see
docs/deployment/docker.md.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
COMPOSE = (ROOT / "docker-compose.yml").read_text()
DOCKERIGNORE = (ROOT / ".dockerignore").read_text().splitlines()
INIT_SQL = (ROOT / "docker/postgres/initdb.d/10-create-test-database.sql").read_text()


def _instructions(text: str) -> list[tuple[str, str]]:
    """Dockerfile instructions as (KEYWORD, arguments): continuations joined, comments dropped."""
    result = []
    for line in re.sub(r"\\\n", " ", text).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keyword, _, rest = line.partition(" ")
            result.append((keyword.upper(), rest.strip()))
    return result


INSTRUCTIONS = _instructions(DOCKERFILE)
LAST_FROM = max(i for i, (keyword, _) in enumerate(INSTRUCTIONS) if keyword == "FROM")
FINAL_STAGE = INSTRUCTIONS[LAST_FROM:]


def _final(keyword: str) -> list[str]:
    return [args for kw, args in FINAL_STAGE if kw == keyword]


# --- Dockerfile -----------------------------------------------------------------------------


def test_the_final_image_runs_as_a_numeric_non_root_user() -> None:
    users = _final("USER")
    assert users, "the final stage never sets USER, so it would run as root"
    uid = users[-1].split(":")[0]
    assert uid.isdigit(), "use a numeric UID so an orchestrator can verify it is not root"
    assert int(uid) != 0


def test_base_images_are_pinned_to_a_tag_and_never_latest() -> None:
    images = [args.split()[0] for keyword, args in INSTRUCTIONS if keyword == "FROM"]
    assert images
    for image in images:
        assert ":" in image, f"{image} has no tag"
        assert not image.endswith(":latest"), f"{image} floats"


def test_cmd_is_in_exec_form_so_the_server_is_pid_1() -> None:
    commands = _final("CMD")
    assert commands
    assert commands[-1].startswith("[")


def test_the_image_defines_a_health_check() -> None:
    assert _final("HEALTHCHECK")


def test_only_the_application_port_is_exposed() -> None:
    assert _final("EXPOSE") == ["8000"]


def test_python_output_is_unbuffered_so_logs_reach_stdout() -> None:
    assert any("PYTHONUNBUFFERED=1" in args for args in _final("ENV"))


def test_no_secret_like_names_appear_in_env_or_arg() -> None:
    forbidden = re.compile(r"PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY", re.IGNORECASE)
    for keyword, args in INSTRUCTIONS:
        if keyword in {"ENV", "ARG"}:
            assert not forbidden.search(args), f"{keyword} {args}"


def test_remote_scripts_are_never_piped_into_a_shell() -> None:
    assert not re.search(r"(curl|wget)[^\n|]*\|\s*(sh|bash)", DOCKERFILE)


def test_the_runtime_stage_copies_what_the_application_needs() -> None:
    copied = " ".join(_final("COPY"))
    for needed in ("/app/.venv", "alembic.ini", "migrations", "app", "worker"):
        assert needed in copied, f"runtime stage does not copy {needed}"


def test_the_dependency_install_uses_the_lock_file_without_re_resolving() -> None:
    installs = [args for keyword, args in INSTRUCTIONS if keyword == "RUN" and "uv sync" in args]
    assert installs
    assert all("--frozen" in args and "--no-dev" in args for args in installs)


# --- .dockerignore --------------------------------------------------------------------------


def test_dockerignore_keeps_secrets_and_history_out_of_the_build_context() -> None:
    assert ".env" in DOCKERIGNORE
    assert ".git" in DOCKERIGNORE


def test_dockerignore_does_not_exclude_what_the_build_needs() -> None:
    for needed in ("pyproject.toml", "uv.lock", "app", "worker", "migrations", "alembic.ini"):
        assert needed not in DOCKERIGNORE
        assert f"{needed}/" not in DOCKERIGNORE


# --- docker-compose.yml ---------------------------------------------------------------------


def test_compose_publishes_ports_on_loopback_only() -> None:
    ports = re.findall(r'^\s*-\s*"([^"]+:\d+)"\s*$', COMPOSE, re.MULTILINE)
    assert ports
    for port in ports:
        assert port.startswith("127.0.0.1:"), f"{port} is reachable from the network"


def test_compose_has_no_literal_passwords() -> None:
    for line in COMPOSE.splitlines():
        if "PASSWORD" in line and not line.lstrip().startswith("#"):
            assert "${" in line, f"literal password: {line.strip()}"


def test_compose_hardens_the_application_containers() -> None:
    assert "read_only: true" in COMPOSE
    assert "cap_drop:" in COMPOSE
    assert "no-new-privileges:true" in COMPOSE


def test_the_integration_test_database_is_created_with_a_test_suffix() -> None:
    assert re.search(r"CREATE DATABASE app_test\b", INIT_SQL)


def test_redis_is_not_in_the_stack_because_nothing_uses_it() -> None:
    assert "redis" not in COMPOSE.lower()
