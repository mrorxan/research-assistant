"""Shared fixtures for Topic 4 smoke tests."""

from __future__ import annotations

from typing import Any

import pytest

from ai.providers.base import LLMProvider
from ai.schemas import Source
from ai.sources import WebSearchProvider
from researcher.config import Settings


class FakeLLM(LLMProvider):
    """Returns a fixed text response. Records calls for inspection."""

    def __init__(self, response: str | None = None) -> None:
        self.response = response or (
            "Photosynthesis is the process by which plants convert light "
            "energy into chemical energy [1]. The reaction takes place in "
            "the chloroplasts and produces oxygen as a byproduct [2]."
        )
        self.calls: list[str] = []

    def complete(
        self,
        prompt: str,
        *,
        json_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> str:
        self.calls.append(prompt)
        return self.response


class FakeWebSearch(WebSearchProvider):
    """Returns canned web results without touching the network."""

    def __init__(self, results: list[Source] | None = None) -> None:
        self.results = results or [
            Source(
                title="Photosynthesis — Encyclopedia",
                url="https://example.com/photosynthesis",
                snippet="A biological process used by plants and some bacteria.",
                origin="web",
            )
        ]
        self.calls: list[str] = []

    async def search(
        self,
        query: str,
        *,
        max_results: int = 3,
        client: Any = None,
    ) -> list[Source]:
        self.calls.append(query)
        return self.results[:max_results]


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def fake_web() -> FakeWebSearch:
    return FakeWebSearch()


@pytest.fixture
def sample_sources() -> list[Source]:
    return [
        Source(
            title="Photosynthesis (Wikipedia)",
            url="https://en.wikipedia.org/wiki/Photosynthesis",
            snippet="Photosynthesis is a process used by plants and other organisms "
                    "to convert light energy into chemical energy.",
            origin="wikipedia",
        ),
        Source(
            title="Calvin cycle (Wikipedia)",
            url="https://en.wikipedia.org/wiki/Calvin_cycle",
            snippet="The Calvin cycle is a series of biochemical redox reactions "
                    "in the stroma of chloroplasts.",
            origin="wikipedia",
        ),
    ]


<<<<<<< HEAD
# SE-layer fixtures. Everything above this line belongs to the provided
# smoke-test contract and keeps its names unchanged.


=======
>>>>>>> e523a590d4bf134c0e2d6eeb6646e6af3d1917dd
@pytest.fixture
def tmp_cache_dir(tmp_path):
    directory = tmp_path / "cache"
    directory.mkdir()
    return directory


@pytest.fixture
def fast_settings(tmp_cache_dir, tmp_path) -> Settings:
    """Settings tuned for fast tests: tiny backoff, short timeouts, tmp cache."""
    return Settings(
        LLM_PROVIDER="gemini",
        LLM_MODEL="gemini-2.5-flash-lite",
        WEB_SEARCH_PROVIDER="tavily",
        LOG_LEVEL="WARNING",
        CACHE_DIR=tmp_cache_dir,
        CACHE_TTL_SECONDS=60,
        COST_LOG_PATH=tmp_path / "costs.jsonl",
        PER_SOURCE_TIMEOUT_SECONDS=0.5,
        SYNTHESIZE_TIMEOUT_SECONDS=1.0,
        MAX_SOURCES_PER_QUERY=2,
        MAX_PARALLEL=3,
        MAX_QUESTION_LENGTH=120,
        RETRY_MAX_ATTEMPTS=2,
        RETRY_BACKOFF_MIN=0.01,
        RETRY_BACKOFF_MAX=0.02,
    )


@pytest.fixture
def wikipedia_source() -> Source:
    return Source(
        title="Test Wiki Article",
        url="https://en.wikipedia.org/wiki/Test",
        snippet="Wikipedia summary text.",
        origin="wikipedia",
    )


@pytest.fixture
def arxiv_source() -> Source:
    return Source(
        title="Test arXiv Paper",
        url="https://arxiv.org/abs/0001.0001",
        snippet="arXiv abstract text.",
        origin="arxiv",
    )


@pytest.fixture
def web_source() -> Source:
    return Source(
        title="Test Web Result",
        url="https://example.com/article",
        snippet="Web search result snippet.",
        origin="web",
    )
