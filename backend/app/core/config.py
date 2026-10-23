from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read configuration from environment variables and an optional local file."""

    model_config = SettingsConfigDict(
        env_prefix="HISSIYAT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    service_name: str = "Hissiyat API"
    environment: Literal["development", "test", "production"] = "development"

    database_host: str = "127.0.0.1"
    database_port: int = Field(default=55432, ge=1, le=65535)
    database_name: str | None = None
    database_user: str | None = None
    database_password: SecretStr | None = Field(default=None, repr=False)
    database_connect_timeout: int = Field(default=3, ge=1, le=30)
    database_pool_timeout: int = Field(default=2, ge=1, le=30)
    database_statement_timeout_ms: int = Field(default=3000, ge=1, le=30000)

    @field_validator("database_host", "database_name", "database_user")
    @classmethod
    def reject_blank_database_settings(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Database settings must not be blank.")
        return value

    @field_validator("database_password")
    @classmethod
    def reject_blank_database_password(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("Database password must not be blank.")
        return value

    @property
    def database_is_configured(self) -> bool:
        return all(
            value is not None
            for value in (self.database_name, self.database_user, self.database_password)
        )
