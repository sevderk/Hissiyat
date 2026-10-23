from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import URL, Connection, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings


class DatabaseConfigurationError(ValueError):
    """Report missing database configuration without including its values."""


class Database:
    """Manage a small, lazy SQLAlchemy Core connection pool using psycopg."""

    def __init__(self, settings: Settings) -> None:
        if not settings.database_is_configured:
            raise DatabaseConfigurationError("Required database configuration is missing.")

        url = URL.create(
            drivername="postgresql+psycopg",
            host=settings.database_host,
            port=settings.database_port,
            database=settings.database_name,
            username=settings.database_user,
            password=settings.database_password.get_secret_value(),
        )
        self._engine = create_engine(
            url,
            pool_size=2,
            max_overflow=0,
            pool_timeout=settings.database_pool_timeout,
            pool_pre_ping=True,
            connect_args={
                "connect_timeout": settings.database_connect_timeout,
                "options": f"-c statement_timeout={settings.database_statement_timeout_ms}",
            },
            echo=False,
            hide_parameters=True,
        )

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        """Release the connection and roll back any uncommitted work on exit."""
        with self._engine.connect() as connection:
            yield connection

    def check_connection(self) -> bool:
        try:
            with self.connection() as connection:
                return connection.execute(text("SELECT 1")).scalar_one() == 1
        except (SQLAlchemyError, OSError):
            # Driver errors can contain connection details: do not log or return them.
            return False

    def close(self) -> None:
        self._engine.dispose()
