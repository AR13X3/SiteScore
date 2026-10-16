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
    hf_token: str | None = Field(None, validation_alias="HF_TOKEN")
    region: str = Field("parramatta", validation_alias="SITESCORE_REGION")
    offline: bool = Field(False, validation_alias="SITESCORE_OFFLINE")
    force_mock: bool = Field(False, validation_alias="SITESCORE_FORCE_MOCK")
    # Score the region-wide opportunity map in the background at startup (~10 s), so the
    # first visitor to the overview doesn't wait for it.
    warm_heatmap: bool = Field(True, validation_alias="SITESCORE_WARM_HEATMAP")
    # AI analyst (optional): any OpenRouter model that supports tool calling.
    openrouter_api_key: str | None = Field(None, validation_alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field("anthropic/claude-haiku-5.5", validation_alias="OPENROUTER_MODEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
