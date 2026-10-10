"""Module-local provider settings; no credentials are logged or exposed to clients."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import ROOT


class IntelligenceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", validate_assignment=True
    )
    openai_api_key: SecretStr = SecretStr("")
    openai_assessment_model: Literal["gpt-6-luna"] = "gpt-6-luna"
    # Explicitly configure a supported Responses model before enabling extraction.
    openai_extraction_model: str | None = None
    openai_emergency_model: str = Field(default="gpt-6-luna", min_length=1)
    openai_intelligence_timeout_seconds: float = Field(default=15, gt=0, le=15)
