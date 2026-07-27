"""ResearchSession serialisation and defaults."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai.schemas import AnswerWithCitations, Citation, Source
from researcher.models import ResearchSession


def _session(**overrides) -> ResearchSession:
    source = Source(title="t", url="u", snippet="s", origin="web")
    answer = AnswerWithCitations(
        question="Q",
        answer="A [1]",
        citations=[Citation(index=1, source=source)],
    )
    fields = {
        "question": "Q",
        "sources_used": [source],
        "answer": answer,
        "duration_ms": 12,
    }
    fields.update(overrides)
    return ResearchSession(**fields)


def test_to_dict_flattens_answer_and_sources():
    data = _session().to_dict()
    assert data["question"] == "Q"
    assert data["duration_ms"] == 12
    assert data["answer"]["citations"][0]["title"] == "t"
    assert data["sources_used"][0]["origin"] == "web"
    assert "T" in data["started_at"]


def test_cache_hits_and_failed_sources_default_empty():
    session = _session()
    assert session.cache_hits == {}
    assert session.failed_sources == []


def test_extra_fields_are_forbidden():
    with pytest.raises(ValidationError):
        _session(unexpected_field=1)
