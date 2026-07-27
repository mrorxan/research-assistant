"""End-to-end flows with every ai.* call mocked at the module boundary."""

from __future__ import annotations

import pytest

from ai.schemas import AnswerWithCitations
from researcher.cli import build_researcher
from researcher.services import ai_service as ai_service_module


def _install_mocks(monkeypatch, wikipedia_source, arxiv_source, web_source, call_count=None):
    async def mock_wikipedia(query, *, max_results, client=None):
        if call_count is not None:
            call_count["wikipedia"] += 1
        return [wikipedia_source]

    async def mock_arxiv(query, *, max_results, client=None):
        if call_count is not None:
            call_count["arxiv"] += 1
        return [arxiv_source]

    async def mock_web(query, *, max_results, provider=None, client=None):
        if call_count is not None:
            call_count["web"] += 1
        return [web_source]

    def mock_synthesize(question, sources, *, llm=None):
        return AnswerWithCitations(
            question=question, answer="Mocked answer [1][2][3].", citations=[],
        )

    monkeypatch.setattr(ai_service_module, "fetch_wikipedia", mock_wikipedia)
    monkeypatch.setattr(ai_service_module, "fetch_arxiv", mock_arxiv)
    monkeypatch.setattr(ai_service_module, "fetch_web", mock_web)
    monkeypatch.setattr(ai_service_module, "synthesize", mock_synthesize)

@pytest.mark.asyncio
async def test_full_ask_flow(monkeypatch, fast_settings, wikipedia_source,
                             arxiv_source, web_source):
    _install_mocks(monkeypatch, wikipedia_source, arxiv_source, web_source)
    researcher = build_researcher(fast_settings, bypass_cache=False)
    session = await researcher.ask("What is photosynthesis?")
    assert session.question == "What is photosynthesis?"
    assert len(session.sources_used) == 3
    assert "Mocked answer" in session.answer.answer
    assert session.failed_sources == []
    assert session.cache_hits == {"wikipedia": False, "arxiv": False, "web": False}

@pytest.mark.asyncio
async def test_second_ask_hits_cache(monkeypatch, fast_settings, wikipedia_source,
                                     arxiv_source, web_source):
    call_count = {"wikipedia": 0, "arxiv": 0, "web": 0}
    _install_mocks(monkeypatch, wikipedia_source, arxiv_source, web_source, call_count)
    researcher = build_researcher(fast_settings, bypass_cache=False)
    await researcher.ask("What is photosynthesis?")
    second = await researcher.ask("What is photosynthesis?")
    assert call_count == {"wikipedia": 1, "arxiv": 1, "web": 1}
    assert second.cache_hits == {"wikipedia": True, "arxiv": True, "web": True}