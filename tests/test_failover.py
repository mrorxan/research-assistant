"""FailoverLLM: chaos tests for the multi-provider bonus."""

from __future__ import annotations

import pytest

from ai.providers.base import LLMProvider, ProviderError
from researcher.config import Settings
from researcher.services.failover import FailoverLLM, build_llm


class HealthyLLM(LLMProvider):
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def complete(self, prompt, *, json_schema=None, max_tokens=1024):
        self.calls += 1
        return self.reply

class DownLLM(LLMProvider):
    def complete(self, prompt, *, json_schema=None, max_tokens=1024):
        raise ProviderError("upstream down")

def test_primary_success_never_touches_fallback():
    primary = HealthyLLM("from primary")
    built = {"fallback": False}

    def fallback_factory():
        built["fallback"] = True
        return HealthyLLM("from fallback")

    llm = FailoverLLM([("primary", lambda: primary), ("fallback", fallback_factory)])
    assert llm.complete("anything") == "from primary"
    assert built["fallback"] is False

def test_fallback_used_when_primary_call_fails():
    llm = FailoverLLM([
        ("primary", lambda: DownLLM()),
        ("fallback", lambda: HealthyLLM("from fallback")),
    ])
    assert llm.complete("anything") == "from fallback"

def test_fallback_used_when_primary_construction_fails():
    def broken_factory():
        raise ProviderError("API key is not set")

    llm = FailoverLLM([
        ("primary", broken_factory),
        ("fallback", lambda: HealthyLLM("from fallback")),
    ])
    assert llm.complete("anything") == "from fallback"

def test_all_providers_failing_raises():
    llm = FailoverLLM([
        ("a", lambda: DownLLM()),
        ("b", lambda: DownLLM()),
    ])
    with pytest.raises(ProviderError, match="all LLM providers failed"):
        llm.complete("anything")

def test_provider_instance_is_reused_between_calls():
    primary = HealthyLLM("ok")
    llm = FailoverLLM([("primary", lambda: primary)])
    llm.complete("one")
    llm.complete("two")
    assert primary.calls == 2

def test_empty_factory_list_is_rejected():
    with pytest.raises(ValueError):
        FailoverLLM([])

def test_build_llm_returns_none_without_fallback(fast_settings):
    assert build_llm(fast_settings) is None

def test_build_llm_returns_failover_chain(tmp_path):
    settings = Settings(
        LLM_PROVIDER="gemini",
        LLM_FALLBACK_PROVIDER="anthropic",
        CACHE_DIR=tmp_path / "cache",
    )
    llm = build_llm(settings)
    assert isinstance(llm, FailoverLLM)

def test_concrete_factory_rejects_unknown_provider():
    from researcher.services.failover import _concrete_factory

    factory = _concrete_factory("acme", None)
    with pytest.raises(ProviderError, match="Unknown LLM provider"):
        factory()

def test_gemini_factory_without_key_raises_provider_error(monkeypatch):
    from researcher.services.failover import _concrete_factory

    for var in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    factory = _concrete_factory("gemini", "gemini-2.5-flash-lite")
    with pytest.raises(ProviderError):
        factory()

def test_missing_key_on_primary_falls_back_end_to_end(monkeypatch):
    from researcher.services.failover import _concrete_factory

    for var in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    llm = FailoverLLM([
        ("gemini", _concrete_factory("gemini", None)),
        ("fallback", lambda: HealthyLLM("rescued")),
    ])
    assert llm.complete("anything") == "rescued"
