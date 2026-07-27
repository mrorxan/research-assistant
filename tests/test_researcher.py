"""Researcher: validation rules, happy path, no-sources failure."""

from __future__ import annotations

import pytest

from ai.providers.base import ProviderError
from ai.schemas import AnswerWithCitations
from researcher.concurrency.orchestrator import FetchOutcome, SourceResult
from researcher.core.researcher import (
    QuestionValidationError,
    Researcher,
    validate_question,
)


class FakeOrchestrator:
    def __init__(self, outcome):
        self._outcome = outcome
        self.last_call = None

    async def fetch(self, query, *, sources=None, client=None):
        self.last_call = (query, sources)
        return self._outcome

class FakeAI:
    def __init__(self, answer):
        self._answer = answer
        self.calls = []

    async def synthesize(self, question, sources, *, llm=None):
        self.calls.append((question, len(sources), llm))
        return self._answer

def test_validate_rejects_empty():
    with pytest.raises(QuestionValidationError):
        validate_question("   ", max_length=100)

def test_validate_rejects_too_long():
    with pytest.raises(QuestionValidationError):
        validate_question("x" * 101, max_length=100)

def test_validate_trims_whitespace():
    assert validate_question("  hello  ", max_length=100) == "hello"

@pytest.mark.asyncio
async def test_ask_happy_path(wikipedia_source, arxiv_source):
    outcome = FetchOutcome(
        sources=[wikipedia_source, arxiv_source],
        results=[
            SourceResult("wikipedia", [wikipedia_source], None, False),
            SourceResult("arxiv", [arxiv_source], None, True),
            SourceResult("web", [], "timeout", False),
        ],
        failed=["web"],
    )
    answer = AnswerWithCitations(question="Q", answer="A [1]", citations=[])
    fake_ai = FakeAI(answer)
    researcher = Researcher(fake_ai, FakeOrchestrator(outcome), max_question_length=200)
    session = await researcher.ask("What is photosynthesis?")
    assert session.answer is answer
    assert session.failed_sources == ["web"]
    assert session.cache_hits == {"wikipedia": False, "arxiv": True, "web": False}
    assert session.duration_ms >= 0
    assert fake_ai.calls[0][1] == 2

@pytest.mark.asyncio
async def test_ask_raises_when_every_source_fails():
    outcome = FetchOutcome(sources=[], results=[], failed=["wikipedia", "arxiv", "web"])
    researcher = Researcher(FakeAI(None), FakeOrchestrator(outcome), max_question_length=200)
    with pytest.raises(ProviderError):
        await researcher.ask("Q")

@pytest.mark.asyncio
async def test_ask_propagates_validation_error():
    researcher = Researcher(FakeAI(None), FakeOrchestrator(None), max_question_length=10)
    with pytest.raises(QuestionValidationError):
        await researcher.ask("")

@pytest.mark.asyncio
async def test_ask_forwards_source_subset(wikipedia_source):
    outcome = FetchOutcome(
        sources=[wikipedia_source],
        results=[SourceResult("wikipedia", [wikipedia_source], None, False)],
        failed=[],
    )
    answer = AnswerWithCitations(question="Q", answer="A", citations=[])
    orchestrator = FakeOrchestrator(outcome)
    researcher = Researcher(FakeAI(answer), orchestrator, max_question_length=200)
    await researcher.ask("Q", sources=["wikipedia"])
    assert orchestrator.last_call == ("Q", ["wikipedia"])
