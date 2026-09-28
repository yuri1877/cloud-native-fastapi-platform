import pytest
from pydantic import ValidationError

from app.core.config import Settings

DB_URL = "postgresql+asyncpg://user:s3cret@localhost:5432/app"


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "dev"
    assert settings.log_level == "INFO"
    assert settings.docs_enabled is True
    assert settings.database_url is None
    assert (settings.db_pool_size, settings.db_max_overflow) == (5, 10)
    assert settings.db_pool_timeout == 30
    assert settings.db_pool_recycle == 1800
    assert settings.db_echo is False


def test_environment_variables_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("DB_POOL_SIZE", "20")
    settings = Settings(_env_file=None)
    assert settings.app_env == "prod"
    assert settings.log_level == "WARNING"
    assert settings.docs_enabled is False
    assert settings.db_pool_size == 20


def test_invalid_environment_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "banana")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_url_is_secret() -> None:
    settings = Settings(_env_file=None, database_url=DB_URL)
    assert settings.database_url is not None
    assert settings.database_url.get_secret_value() == DB_URL
    assert "s3cret" not in repr(settings)
    assert "s3cret" not in str(settings)


def test_database_url_requires_asyncpg_scheme_without_leaking_it() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, database_url="postgresql://user:s3cret@localhost/app")
    assert "s3cret" not in str(excinfo.value)


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_database_url_required_outside_dev(env: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env=env)
    assert Settings(_env_file=None, app_env=env, database_url=DB_URL).app_env == env


def test_pool_bounds_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, db_pool_size=0)
