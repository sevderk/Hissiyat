from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_endpoint_returns_json() -> None:
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_health_endpoint_requires_versioned_path() -> None:
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        assert client.get("/health").status_code == 404


def test_environment_configures_service(monkeypatch) -> None:
    monkeypatch.setenv("HISSIYAT_SERVICE_NAME", "Hissiyat Test API")
    monkeypatch.setenv("HISSIYAT_ENVIRONMENT", "test")
    application = create_app(Settings(_env_file=None))

    assert application.title == "Hissiyat Test API"
    assert application.state.settings.environment == "test"
