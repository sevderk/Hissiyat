from pathlib import Path
import socket

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def test_database_settings() -> Settings:
    settings = Settings(_env_file=Path(__file__).resolve().parents[2] / ".env.test")
    if (
        not settings.database_is_configured
        or settings.database_name != "hissiyat_test"
        or settings.database_host != "127.0.0.1"
        or settings.environment != "test"
    ):
        pytest.fail("Integration tests require the isolated local hissiyat_test configuration.")
    return settings


def test_real_postgres_connection(test_database_settings) -> None:
    database = Database(test_database_settings)
    try:
        with database.connection() as connection:
            assert connection.execute(text("SELECT current_database()")).scalar_one() == "hissiyat_test"
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        database.close()


def test_readiness_with_real_postgres(test_database_settings) -> None:
    with TestClient(create_app(test_database_settings)) as client:
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "database": "ok"}
        assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_unreachable_postgres_keeps_liveness(test_database_settings) -> None:
    # Reserve a local port without listening; no existing database is interrupted.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved_port:
        reserved_port.bind(("127.0.0.1", 0))
        settings = test_database_settings.model_copy(update={
            "database_port": reserved_port.getsockname()[1],
            "database_connect_timeout": 1,
        })
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/v1/health").status_code == 200
            response = client.get("/api/v1/health/ready")
            assert response.status_code == 503
            assert response.json() == {"status": "unavailable", "database": "unavailable"}
