from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.database import Database


def make_database(monkeypatch):
    engine = MagicMock()
    factory = MagicMock(return_value=engine)
    monkeypatch.setattr("app.core.database.create_engine", factory)
    database = Database(Settings(
        _env_file=None,
        database_name="unit_test",
        database_user="unit_user",
        database_password="unit-password-canary",
    ))
    return database, engine, factory


def test_connection_success_and_release(monkeypatch) -> None:
    database, engine, factory = make_database(monkeypatch)
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = 1

    assert database.check_connection()
    engine.connect.return_value.__exit__.assert_called_once()
    url = factory.call_args.args[0]
    assert url.drivername == "postgresql+psycopg"
    assert "unit-password-canary" not in str(url)
    assert factory.call_args.kwargs["connect_args"]["connect_timeout"] == 3
    assert factory.call_args.kwargs["echo"] is False


def test_database_failure_does_not_log_details(monkeypatch, caplog) -> None:
    database, engine, _ = make_database(monkeypatch)
    engine.connect.side_effect = OperationalError(
        "SELECT 1", {}, Exception("unit-password-canary private-host")
    )

    assert database.check_connection() is False
    assert "unit-password-canary" not in caplog.text
    assert "private-host" not in caplog.text


def test_pool_is_disposed(monkeypatch) -> None:
    database, engine, _ = make_database(monkeypatch)
    database.close()
    engine.dispose.assert_called_once()
