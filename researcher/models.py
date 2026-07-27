"""Pydantic models that cross the SE-layer module boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai.schemas import AnswerWithCitations, Source


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ResearchSession(BaseModel):
    """One ask-to-answer round trip with timing and per-source outcome."""

    model_config = ConfigDict(extra="forbid")

    question: str
    sources_used: list[Source]
    answer: AnswerWithCitations
    duration_ms: int
    cache_hits: dict[str, bool] = Field(default_factory=dict)
    failed_sources: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "duration_ms": self.duration_ms,
            "cache_hits": self.cache_hits,
            "failed_sources": self.failed_sources,
            "started_at": self.started_at.isoformat(),
            "answer": self.answer.to_dict(),
            "sources_used": [s.model_dump() for s in self.sources_used],
        }