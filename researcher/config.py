"""Typed application settings loaded from environment variables or .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-2.5-flash-lite", alias="LLM_MODEL")
    llm_fallback_provider: str = Field(default="", alias="LLM_FALLBACK_PROVIDER")
    llm_fallback_model: str = Field(default="", alias="LLM_FALLBACK_MODEL")
    web_search_provider: str = Field(default="tavily", alias="WEB_SEARCH_PROVIDER")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cache_dir: Path = Field(default=Path("./.cache"), alias="CACHE_DIR")
    cache_ttl_seconds: int = Field(default=86400, alias="CACHE_TTL_SECONDS")
    cost_log_path: Path = Field(default=Path("./.cache/costs.jsonl"), alias="COST_LOG_PATH")

    per_source_timeout_seconds: float = Field(default=15.0, alias="PER_SOURCE_TIMEOUT_SECONDS")
    synthesize_timeout_seconds: float = Field(default=60.0, alias="SYNTHESIZE_TIMEOUT_SECONDS")
    max_sources_per_query: int = Field(default=3, alias="MAX_SOURCES_PER_QUERY")
    max_parallel: int = Field(default=3, alias="MAX_PARALLEL")
    max_question_length: int = Field(default=500, alias="MAX_QUESTION_LENGTH")

    retry_max_attempts: int = Field(default=3, alias="RETRY_MAX_ATTEMPTS")
    retry_backoff_min: float = Field(default=1.0, alias="RETRY_BACKOFF_MIN")
    retry_backoff_max: float = Field(default=8.0, alias="RETRY_BACKOFF_MAX")

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        level = value.upper().strip()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}, got {value!r}")
        return level

    @field_validator("max_sources_per_query", "max_parallel", "max_question_length", "retry_max_attempts")
    @classmethod
    def _validate_positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be at least 1")
        return value

    @field_validator("per_source_timeout_seconds", "synthesize_timeout_seconds", "retry_backoff_min", "retry_backoff_max")
    @classmethod
    def _validate_positive_float(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be greater than 0")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
