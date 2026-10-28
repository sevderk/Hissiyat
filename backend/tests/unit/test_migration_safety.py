"""Deterministic simulations only; mocks do not establish live server identity."""

from contextlib import nullcontext
import runpy
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from alembic import context
from alembic.config import Config
from alembic.util import CommandError
from psycopg import Connection as PsycopgConnection
from psycopg.pq import ConnStatus
import pytest
from sqlalchemy import Connection, URL

from app.core import migrations
from app.core.config import Settings
from app.core.migrations import (
    BACKEND_ROOT, MigrationSafetyError, inspect_migration_state,
    validate_connection_target, validate_operation, validate_target,
)


def settings(**overrides):
    values = dict(
        _env_file=None, environment="test", database_host="127.0.0.1", database_port=55432,
        database_name="hissiyat_test", database_user="synthetic_user", database_password="synthetic-only",
    )
    return Settings(**(values | overrides))


@pytest.mark.parametrize("field,value", [
    ("database_host", "localhost"), ("database_host", "192.0.2.1"),
    ("database_port", 54322), ("database_name", "hissiyat_dev"),
    ("database_name", "unrelated"), ("environment", "development"),
    ("database_password", None), ("database_user", None),
])
def test_migration_rejects_wrong_or_incomplete_target(field, value):
    with pytest.raises(MigrationSafetyError):
        validate_target(settings(**{field: value}), "test")


def test_only_exact_local_development_and_test_targets_are_allowed():
    validate_target(settings(), "test")
    validate_target(settings(environment="development", database_name="hissiyat_dev"), "development")
    with pytest.raises(MigrationSafetyError):
        validate_target(settings(), "production")


def test_development_upgrade_requires_deliberate_opt_in():
    with pytest.raises(MigrationSafetyError, match="explicit approval"):
        validate_operation("upgrade", "development")
    validate_operation("upgrade", "development", allow_development=True)
    validate_operation("upgrade", "test")


@pytest.mark.parametrize("operation", ["current", "check"])
def test_read_only_inspection_does_not_require_development_upgrade_flag(operation):
    validate_operation(operation, "development")


@pytest.mark.parametrize("operation", ["downgrade", "stamp", "revision", ""])
def test_unapproved_migration_operations_are_rejected(operation):
    with pytest.raises(MigrationSafetyError):
        validate_operation(operation, "test")


@pytest.fixture
def supplied_connection():
    driver = MagicMock(spec=PsycopgConnection)
    driver.closed = False
    driver.broken = False
    driver.pgconn = SimpleNamespace(status=ConnStatus.OK)
    driver.info = SimpleNamespace(host="127.0.0.1", hostaddr="127.0.0.1", port=55432, dbname="hissiyat_test")
    connection = MagicMock(spec=Connection)
    connection.closed = False
    connection.invalidated = False
    connection.dialect = SimpleNamespace(name="postgresql", driver="psycopg")
    connection.engine = SimpleNamespace(url=URL.create(
        "postgresql+psycopg", host="127.0.0.1", port=55432, database="hissiyat_test",
    ))
    connection.connection = SimpleNamespace(driver_connection=driver)
    connection.in_transaction.return_value = True
    return connection


@pytest.fixture
def migration_environment(monkeypatch, supplied_connection):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes.update(target="test", operation="upgrade", connection=supplied_connection)
    inspect_state = MagicMock(return_value="empty")
    configure = MagicMock()
    execute = MagicMock()
    monkeypatch.setattr(migrations, "migration_settings", lambda target: settings())
    monkeypatch.setattr(migrations, "inspect_migration_state", inspect_state)
    monkeypatch.setattr(context, "config", config, raising=False)
    monkeypatch.setattr(context, "get_x_argument", lambda **kwargs: {})
    monkeypatch.setattr(context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(context, "configure", configure)
    monkeypatch.setattr(context, "begin_transaction", lambda: nullcontext())
    monkeypatch.setattr(context, "run_migrations", execute)
    return SimpleNamespace(
        run=lambda: runpy.run_path(str(BACKEND_ROOT / "migrations/env.py")),
        connection=supplied_connection, inspect_state=inspect_state, configure=configure, execute=execute,
    )


def assert_rejected_before_migration(environment):
    with pytest.raises(CommandError):
        environment.run()
    environment.inspect_state.assert_not_called()
    environment.configure.assert_not_called()
    environment.execute.assert_not_called()
    environment.connection.execute.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("host", "192.0.2.1"), ("hostaddr", "192.0.2.1"), ("port", 54322),
    ("dbname", "hissiyat_dev"), ("host", ""), ("hostaddr", ""),
    ("port", None), ("port", "55432"), ("port", True), ("dbname", None),
])
def test_actual_driver_destination_must_match_despite_matching_engine_url(migration_environment, field, value):
    setattr(migration_environment.connection.connection.driver_connection.info, field, value)
    assert_rejected_before_migration(migration_environment)


@pytest.mark.parametrize("case", [
    "closed_connection", "invalidated_connection", "inactive_transaction", "unknown_transaction",
    "unsupported_dialect", "unsupported_driver", "missing_driver", "unknown_driver",
    "closed_driver", "broken_driver", "unestablished_driver", "missing_host_metadata",
])
def test_unverifiable_supplied_connections_never_reach_migration(migration_environment, case):
    connection = migration_environment.connection
    driver = connection.connection.driver_connection
    if case == "closed_connection":
        connection.closed = True
    elif case == "invalidated_connection":
        connection.invalidated = True
    elif case == "inactive_transaction":
        connection.in_transaction.return_value = False
    elif case == "unknown_transaction":
        connection.in_transaction.return_value = None
    elif case == "unsupported_dialect":
        connection.dialect.name = "sqlite"
    elif case == "unsupported_driver":
        connection.dialect.driver = "psycopg2"
    elif case == "missing_driver":
        connection.connection.driver_connection = None
    elif case == "unknown_driver":
        connection.connection.driver_connection = object()
    elif case == "closed_driver":
        driver.closed = True
    elif case == "broken_driver":
        driver.broken = True
    elif case == "unestablished_driver":
        driver.pgconn.status = ConnStatus.BAD
    else:
        del driver.info.host
    assert_rejected_before_migration(migration_environment)


def test_valid_supplied_destination_reaches_schema_guard_then_migration(migration_environment):
    migration_environment.run()
    migration_environment.inspect_state.assert_called_once_with(migration_environment.connection, "hissiyat_test")
    migration_environment.configure.assert_called_once()
    migration_environment.execute.assert_called_once()
    migration_environment.connection.execute.assert_not_called()


def test_effective_driver_destination_is_used_instead_of_engine_url(migration_environment):
    migration_environment.connection.engine.url = URL.create(
        "postgresql+psycopg", host="192.0.2.1", port=54322, database="unrelated",
    )
    migration_environment.run()
    migration_environment.execute.assert_called_once()


def test_metadata_exceptions_do_not_expose_connection_details(migration_environment, caplog):
    canary = "SYNTHETIC_PRIVATE_CONNECTION_CANARY"
    with patch.object(type(migration_environment.connection), "connection", new_callable=PropertyMock, create=True) as proxy:
        proxy.side_effect = RuntimeError(canary)
        with pytest.raises(CommandError) as error:
            migration_environment.run()
    assert canary not in str(error.value)
    assert canary not in caplog.text
    migration_environment.inspect_state.assert_not_called()
    migration_environment.configure.assert_not_called()
    migration_environment.execute.assert_not_called()


def test_sql_database_identity_is_checked_after_driver_destination(migration_environment, monkeypatch):
    monkeypatch.setattr(migrations, "inspect_migration_state", inspect_migration_state)
    migration_environment.connection.execute.return_value.scalar_one.return_value = "unrelated"
    with pytest.raises(CommandError, match="does not match"):
        migration_environment.run()
    migration_environment.connection.execute.assert_called_once()
    migration_environment.configure.assert_not_called()
    migration_environment.execute.assert_not_called()


def test_connection_guard_revalidates_authorized_settings(supplied_connection):
    with pytest.raises(MigrationSafetyError):
        validate_connection_target(supplied_connection, settings(database_port=54322))
    supplied_connection.execute.assert_not_called()
