import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.database import Database, DatabaseConfigurationError


def test_database_configuration_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("HISSIYAT_DATABASE_HOST", "127.0.0.1")
    monkeypatch.setenv("HISSIYAT_DATABASE_PORT", "55433")
    monkeypatch.setenv("HISSIYAT_DATABASE_NAME", "unit_test")
    monkeypatch.setenv("HISSIYAT_DATABASE_USER", "unit_user")
    monkeypatch.setenv("HISSIYAT_DATABASE_PASSWORD", "unit-only-canary")
    settings = Settings(_env_file=None)

    assert settings.database_is_configured
    assert settings.database_port == 55433
    assert settings.database_name == "unit_test"
    assert isinstance(settings.database_password, SecretStr)
    assert "unit-only-canary" not in repr(settings)
    assert "unit-only-canary" not in settings.model_dump_json()


@pytest.mark.parametrize("missing", ["database_name", "database_user", "database_password"])
def test_missing_configuration_is_explicit(missing) -> None:
    values = dict(database_name="unit_test", database_user="unit_user", database_password="unit-only")
    values[missing] = None
    settings = Settings(_env_file=None, **values)

    assert not settings.database_is_configured
    with pytest.raises(DatabaseConfigurationError, match="configuration is missing"):
        Database(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_port", 0),
        ("database_port", 65536),
        ("database_port", "invalid"),
        ("database_host", " "),
        ("database_name", ""),
        ("database_user", ""),
        ("database_password", " "),
        ("database_connect_timeout", 0),
        ("database_pool_timeout", 0),
        ("database_statement_timeout_ms", 0),
    ],
)
def test_invalid_configuration_is_rejected(field, value) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_configuration_errors_do_not_echo_inputs() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_port="private-input-canary")
    assert "private-input-canary" not in str(error.value)
