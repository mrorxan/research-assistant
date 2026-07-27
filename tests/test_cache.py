"""CachedAIService: hit/miss flow, bypass, and the no-negative-caching rule."""

from __future__ import annotations

import pytest

from researcher.services.cache import CachedAIService
from researcher.storage.cache_store import CacheStore


class StubInner:
    def __init__(self, results_by_source):
        self._results = results_by_source
        self.calls = {"wikipedia": 0, "arxiv": 0, "web": 0}

    async def fetch_wikipedia(self, query, *, client=None):
        self.calls["wikipedia"] += 1
        return self._results["wikipedia"]

    async def fetch_arxiv(self, query, *, client=None):
        self.calls["arxiv"] += 1
        return self._results["arxiv"]

    async def fetch_web(self, query, *, client=None, provider=None):
        self.calls["web"] += 1
        return self._results["web"]


@pytest.mark.asyncio
async def test_miss_then_hit(tmp_cache_dir, wikipedia_source):
    inner = StubInner({"wikipedia": [wikipedia_source], "arxiv": [], "web": []})
    cached = CachedAIService(inner, CacheStore(tmp_cache_dir, ttl_seconds=60))
    first = await cached.fetch_wikipedia("photosynthesis")
    second = await cached.fetch_wikipedia("photosynthesis")
    assert first.sources == second.sources == [wikipedia_source]
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert inner.calls["wikipedia"] == 1


@pytest.mark.asyncio
async def test_empty_results_are_not_cached(tmp_cache_dir, wikipedia_source):
    inner = StubInner({"wikipedia": [], "arxiv": [], "web": []})
    cached = CachedAIService(inner, CacheStore(tmp_cache_dir, ttl_seconds=60))
    first = await cached.fetch_wikipedia("q")
    assert first.sources == []
    inner._results["wikipedia"] = [wikipedia_source]
    second = await cached.fetch_wikipedia("q")
    assert second.cache_hit is False
    assert second.sources == [wikipedia_source]
    assert inner.calls["wikipedia"] == 2


@pytest.mark.asyncio
async def test_bypass_skips_read_and_write(tmp_cache_dir, wikipedia_source):
    inner = StubInner({"wikipedia": [wikipedia_source], "arxiv": [], "web": []})
    store = CacheStore(tmp_cache_dir, ttl_seconds=60)
    store.put("wikipedia", "q", [{
        "title": "stale", "url": "u", "snippet": "s", "origin": "wikipedia",
    }])
    cached = CachedAIService(inner, store, bypass=True)
    result = await cached.fetch_wikipedia("q")
    assert result.sources == [wikipedia_source]
    assert result.cache_hit is False
    assert store.get("wikipedia", "q")[0]["title"] == "stale"


@pytest.mark.asyncio
async def test_no_store_means_live_every_call(wikipedia_source):
    inner = StubInner({"wikipedia": [wikipedia_source], "arxiv": [], "web": []})
    cached = CachedAIService(inner, store=None)
    await cached.fetch_wikipedia("q")
    await cached.fetch_wikipedia("q")
    assert inner.calls["wikipedia"] == 2


@pytest.mark.asyncio
async def test_sources_cached_independently(tmp_cache_dir, arxiv_source, web_source):
    inner = StubInner({"wikipedia": [], "arxiv": [arxiv_source], "web": [web_source]})
    cached = CachedAIService(inner, CacheStore(tmp_cache_dir, ttl_seconds=60))
    await cached.fetch_arxiv("q")
    await cached.fetch_web("q")
    await cached.fetch_arxiv("q")
    await cached.fetch_web("q")
    assert inner.calls["arxiv"] == 1
    assert inner.calls["web"] == 1