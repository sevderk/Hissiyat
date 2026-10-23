from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.v1.health import get_database
from app.core.config import Settings
from app.main import create_app


def unconfigured_settings() -> Settings:
    return Settings(_env_file=None, database_name=None, database_user=None, database_password=None)


def test_missing_database_preserves_liveness() -> None:
    with TestClient(create_app(unconfigured_settings())) as client:
        assert client.get("/api/v1/health").json() == {"status": "ok"}
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}


def test_readiness_success() -> None:
    application = create_app(unconfigured_settings())
    database = MagicMock()
    database.check_connection.return_value = True
    application.dependency_overrides[get_database] = lambda: database

    with TestClient(application) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readiness_failure_preserves_liveness() -> None:
    application = create_app(unconfigured_settings())
    database = MagicMock()
    database.check_connection.return_value = False
    application.dependency_overrides[get_database] = lambda: database

    with TestClient(application) as client:
        response = client.get("/api/v1/health/ready")
        assert client.get("/api/v1/health").status_code == 200
    assert response.status_code == 503
    assert set(response.json()) == {"status", "database"}


def test_startup_is_lazy_and_shutdown_releases_pool(monkeypatch) -> None:
    database = MagicMock()
    factory = MagicMock(return_value=database)
    monkeypatch.setattr("app.main.Database", factory)
    application = create_app(Settings(
        _env_file=None,
        database_name="unit_test",
        database_user="unit_user",
        database_password="unit-only",
    ))

    with TestClient(application):
        factory.assert_called_once()
        database.check_connection.assert_not_called()
    database.close.assert_called_once()
    assert application.state.database is None
