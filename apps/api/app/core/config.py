"""Settings shared by API modules; keys stay on the server."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str = "postgresql+psycopg://healthgrid:healthgrid_local@localhost:5432/healthgrid"
    openai_api_key: SecretStr = SecretStr("")
    demo_scenario: Literal["beirut"] | None = None
    app_environment: Literal["development", "production"] = "development"
    security_username: str = "healthgrid"
    security_password: SecretStr = SecretStr("")
    security_allowed_hosts: list[str] = ["localhost", "127.0.0.1", "api", "testserver"]
    security_allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    security_max_body_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    security_body_timeout_seconds: float = Field(default=15, gt=0, le=60)
    security_requests_per_minute: int = Field(default=600, ge=1, le=10_000)
    security_writes_per_minute: int = Field(default=120, ge=1, le=1000)
    security_expensive_per_minute: int = Field(default=30, ge=1, le=100)
    security_max_expensive_concurrent: int = Field(default=2, ge=1, le=8)

    @model_validator(mode="after")
    def production_security(self):
        password = self.security_password.get_secret_value()
        if password and (len(password) < 16 or not self.security_username.strip()):
            raise ValueError("Security credentials require a username and at least 16 characters.")
        if self.app_environment == "production":
            if not password:
                raise ValueError(
                    "Production requires SECURITY_PASSWORD; anonymous access is disabled."
                )
            if self.demo_scenario:
                raise ValueError("The simulated approval exercise is restricted to development.")
            if not self.security_allowed_hosts or "*" in self.security_allowed_hosts:
                raise ValueError("Production requires explicit allowed hosts.")
            if not self.security_allowed_origins or any(
                not origin.startswith("https://") for origin in self.security_allowed_origins
            ):
                raise ValueError("Production requires explicit HTTPS browser origins.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
