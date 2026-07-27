"""Settings loading, defaults, and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from researcher.config import Settings

ENV_VARS = [
    "LLM_PROVIDER", "LLM_MODEL", "LLM_FALLBACK_PROVIDER", "WEB_SEARCH_PROVIDER",
    "LOG_LEVEL", "CACHE_DIR", "CACHE_TTL_SECONDS", "PER_SOURCE_TIMEOUT_SECONDS",
    "SYNTHESIZE_TIMEOUT_SECONDS", "MAX_SOURCES_PER_QUERY", "MAX_PARALLEL",
    "MAX_QUESTION_LENGTH", "RETRY_MAX_ATTEMPTS",
]


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


def test_defaults_apply_when_env_is_empty(clean_env):
    settings = Settings()
    assert settings.llm_provider == "gemini"
    assert settings.web_search_provider == "tavily"
    assert settings.log_level == "INFO"
    assert settings.max_parallel == 3
    assert settings.synthesize_timeout_seconds == 60.0


def test_env_overrides_defaults(clean_env, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("MAX_PARALLEL", "10")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    settings = Settings()
    assert settings.llm_provider == "anthropic"
    assert settings.max_parallel == 10
    assert settings.log_level == "DEBUG"


def test_invalid_log_level_is_rejected(clean_env, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "chatty")
    with pytest.raises(ValueError):
        Settings()


def test_non_positive_ints_are_rejected(clean_env, monkeypatch):
    monkeypatch.setenv("MAX_PARALLEL", "0")
    with pytest.raises(ValueError):
        Settings()


def test_non_positive_timeouts_are_rejected(clean_env, monkeypatch):
    monkeypatch.setenv("SYNTHESIZE_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValueError):
        Settings()


def test_cache_dir_is_a_path(clean_env):
    settings = Settings(CACHE_DIR="./somewhere/cache")
    assert isinstance(settings.cache_dir, Path)
    assert settings.cache_dir.name == "cache"
