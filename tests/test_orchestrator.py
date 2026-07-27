"""SourceOrchestrator: parallel fan-out, timeout and exception isolation."""

from __future__ import annotations

import asyncio

import pytest

from researcher.concurrency.orchestrator import SourceOrchestrator
from researcher.services.cache import FetchResult


class ScriptedService:
    """Fake CachedAIService with per-source results, delays, and failures."""

    def __init__(self, results=None, delays=None, raises=None, cache_hits=None):
        self._results = results or {}
        self._delays = delays or {}
        self._raises = raises or {}
        self._cache_hits = cache_hits or {}
        self.calls = {"wikipedia": 0, "arxiv": 0, "web": 0}

    async def _one(self, name):
        self.calls[name] += 1
        if name in self._raises:
            raise self._raises[name]
        if name in self._delays:
            await asyncio.sleep(self._delays[name])
        return FetchResult(
            sources=self._results.get(name, []),
            cache_hit=self._cache_hits.get(name, False),
        )

    async def fetch_wikipedia(self, query, *, client=None):
        return await self._one("wikipedia")

    async def fetch_arxiv(self, query, *, client=None):
        return await self._one("arxiv")

    async def fetch_web(self, query, *, client=None, provider=None):
        return await self._one("web")

@pytest.mark.asyncio
async def test_all_three_sources_run(wikipedia_source, arxiv_source, web_source):
    service = ScriptedService(results={
        "wikipedia": [wikipedia_source], "arxiv": [arxiv_source], "web": [web_source],
    })
    orchestrator = SourceOrchestrator(service, per_source_timeout=1.0, max_parallel=3)
    outcome = await orchestrator.fetch("anything")
    assert {s.origin for s in outcome.sources} == {"wikipedia", "arxiv", "web"}
    assert outcome.failed == []
    assert service.calls == {"wikipedia": 1, "arxiv": 1, "web": 1}

@pytest.mark.asyncio
async def test_timeout_isolates_the_slow_source(wikipedia_source, arxiv_source, web_source):
    service = ScriptedService(
        results={"wikipedia": [wikipedia_source], "arxiv": [arxiv_source], "web": [web_source]},
        delays={"wikipedia": 1.0},
    )
    orchestrator = SourceOrchestrator(service, per_source_timeout=0.05, max_parallel=3)
    outcome = await orchestrator.fetch("anything")
    assert outcome.failed == ["wikipedia"]
    assert {s.origin for s in outcome.sources} == {"arxiv", "web"}

@pytest.mark.asyncio
async def test_exception_isolates_the_broken_source(wikipedia_source, arxiv_source):
    service = ScriptedService(
        results={"wikipedia": [wikipedia_source], "arxiv": [arxiv_source]},
        raises={"web": RuntimeError("boom")},
    )
    orchestrator = SourceOrchestrator(service, per_source_timeout=1.0, max_parallel=3)
    outcome = await orchestrator.fetch("anything")
    assert outcome.failed == ["web"]
    assert len(outcome.sources) == 2

@pytest.mark.asyncio
async def test_subset_only_calls_requested_sources(wikipedia_source, arxiv_source, web_source):
    service = ScriptedService(results={
        "wikipedia": [wikipedia_source], "arxiv": [arxiv_source], "web": [web_source],
    })
    orchestrator = SourceOrchestrator(service, per_source_timeout=1.0, max_parallel=3)
    outcome = await orchestrator.fetch("anything", sources=["wikipedia", "arxiv"])
    assert service.calls == {"wikipedia": 1, "arxiv": 1, "web": 0}
    assert outcome.failed == []

@pytest.mark.asyncio
async def test_all_sources_failing_yields_empty_outcome():
    service = ScriptedService(raises={
        "wikipedia": RuntimeError("a"),
        "arxiv": RuntimeError("b"),
        "web": RuntimeError("c"),
    })
    orchestrator = SourceOrchestrator(service, per_source_timeout=1.0, max_parallel=3)
    outcome = await orchestrator.fetch("anything")
    assert outcome.sources == []
    assert set(outcome.failed) == {"wikipedia", "arxiv", "web"}

@pytest.mark.asyncio
async def test_cache_hit_flags_are_propagated(wikipedia_source, arxiv_source):
    service = ScriptedService(
        results={"wikipedia": [wikipedia_source], "arxiv": [arxiv_source]},
        cache_hits={"wikipedia": True},
    )
    orchestrator = SourceOrchestrator(service, per_source_timeout=1.0, max_parallel=3)
    outcome = await orchestrator.fetch("anything", sources=["wikipedia", "arxiv"])
    hits = {r.name: r.cache_hit for r in outcome.results}
    assert hits == {"wikipedia": True, "arxiv": False}

@pytest.mark.asyncio
async def test_fetches_actually_overlap_in_time(wikipedia_source, arxiv_source, web_source):
    delay = 0.15
    service = ScriptedService(
        results={"wikipedia": [wikipedia_source], "arxiv": [arxiv_source], "web": [web_source]},
        delays={"wikipedia": delay, "arxiv": delay, "web": delay},
    )
    orchestrator = SourceOrchestrator(service, per_source_timeout=1.0, max_parallel=3)
    loop = asyncio.get_running_loop()
    started = loop.time()
    await orchestrator.fetch("anything")
    elapsed = loop.time() - started
    assert elapsed < delay * 2.5
