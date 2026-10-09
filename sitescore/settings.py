"""Runtime settings from environment variables / .env. Secrets live only here."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from sitescore.paths import ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    google_places_api_key: str | None = Field(None, validation_alias="GOOGLE_PLACES_API_KEY")
    tfnsw_api_key: str | None = Field(None, validation_alias="TFNSW_API_KEY")
    region: str = Field("parramatta", validation_alias="SITESCORE_REGION")
    offline: bool = Field(False, validation_alias="SITESCORE_OFFLINE")
    force_mock: bool = Field(False, validation_alias="SITESCORE_FORCE_MOCK")


@lru_cache
def get_settings() -> Settings:
    return Settings()
