"""AIService: retry policy, synthesize timeout, cost recording."""

from __future__ import annotations

import time

import pytest

from ai.providers.base import ProviderError
from ai.schemas import AnswerWithCitations, Source
from researcher.services import ai_service as ai_service_module
from researcher.services.ai_service import AIService
from researcher.telemetry.cost import CostMeter


@pytest.mark.asyncio
async def test_fetch_wikipedia_retries_then_succeeds(monkeypatch, fast_settings, wikipedia_source):
    calls = {"n": 0}

    async def flaky(query, *, max_results, client=None):
        calls["n"] += 1
        if calls["n"] < 2:
            raise ProviderError("transient")
        return [wikipedia_source]

    monkeypatch.setattr(ai_service_module, "fetch_wikipedia", flaky)
    service = AIService(fast_settings)
    result = await service.fetch_wikipedia("x")
    assert result == [wikipedia_source]
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_fetch_wikipedia_raises_after_max_attempts(monkeypatch, fast_settings):
    calls = {"n": 0}

    async def always_down(query, *, max_results, client=None):
        calls["n"] += 1
        raise ProviderError("down")

    monkeypatch.setattr(ai_service_module, "fetch_wikipedia", always_down)
    service = AIService(fast_settings)
    with pytest.raises(ProviderError):
        await service.fetch_wikipedia("x")
    assert calls["n"] == fast_settings.retry_max_attempts


@pytest.mark.asyncio
async def test_value_error_is_not_retried(monkeypatch, fast_settings):
    calls = {"n": 0}

    async def broken(query, *, max_results, client=None):
        calls["n"] += 1
        raise ValueError("programmer error")

    monkeypatch.setattr(ai_service_module, "fetch_arxiv", broken)
    service = AIService(fast_settings)
    with pytest.raises(ValueError):
        await service.fetch_arxiv("x")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_fetch_passes_max_results_from_settings(monkeypatch, fast_settings, arxiv_source):
    seen = {}

    async def fake(query, *, max_results, client=None):
        seen["max_results"] = max_results
        return [arxiv_source]

    monkeypatch.setattr(ai_service_module, "fetch_arxiv", fake)
    await AIService(fast_settings).fetch_arxiv("anything")
    assert seen["max_results"] == fast_settings.max_sources_per_query


@pytest.mark.asyncio
async def test_synthesize_runs_in_thread_and_retries(monkeypatch, fast_settings):
    answer = AnswerWithCitations(question="Q", answer="A [1]", citations=[])
    attempts = {"n": 0}

    def flaky(question, sources, *, llm=None):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ProviderError("transient")
        return answer

    monkeypatch.setattr(ai_service_module, "synthesize", flaky)
    service = AIService(fast_settings)
    source = Source(title="t", url="u", snippet="s", origin="web")
    result = await service.synthesize("Q", [source])
    assert result is answer
    assert attempts["n"] == 2


@pytest.mark.asyncio
async def test_synthesize_timeout_becomes_provider_error(monkeypatch, fast_settings):
    def hangs(question, sources, *, llm=None):
        time.sleep(5)
        return AnswerWithCitations(question="Q", answer="late", citations=[])

    monkeypatch.setattr(ai_service_module, "synthesize", hangs)
    service = AIService(fast_settings)
    source = Source(title="t", url="u", snippet="s", origin="web")
    with pytest.raises(ProviderError, match="timed out"):
        await service.synthesize("Q", [source])


@pytest.mark.asyncio
async def test_synthesize_records_cost(monkeypatch, fast_settings):
    answer = AnswerWithCitations(question="Q", answer="A" * 40, citations=[])

    def fake(question, sources, *, llm=None):
        return answer

    monkeypatch.setattr(ai_service_module, "synthesize", fake)
    meter = CostMeter(fast_settings.cost_log_path)
    service = AIService(fast_settings, meter=meter)
    source = Source(title="t", url="u", snippet="s", origin="web")
    await service.synthesize("Q", [source])
    entries = meter.read_since(1)
    assert len(entries) == 1
    assert entries[0]["model"] == fast_settings.llm_model
    assert entries[0]["completion_tokens"] == 10
