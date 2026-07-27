"""Top-level flow: validate the question, fetch sources, synthesise the answer."""

from __future__ import annotations

import logging
import time
from typing import Any

from ai.providers.base import LLMProvider, ProviderError
from researcher.concurrency.orchestrator import SourceOrchestrator
from researcher.models import ResearchSession
from researcher.services.ai_service import AIService

logger = logging.getLogger(__name__)

class QuestionValidationError(ValueError):
    pass

def validate_question(question: str, *, max_length: int) -> str:
    cleaned = (question or "").strip()
    if not cleaned:
        raise QuestionValidationError("question must not be empty")
    if len(cleaned) > max_length:
        raise QuestionValidationError(
            f"question is too long ({len(cleaned)} chars, max {max_length})"
        )
    return cleaned

class Researcher:
    def __init__(
        self,
        ai: AIService,
        orchestrator: SourceOrchestrator,
        *,
        max_question_length: int,
    ) -> None:
        self._ai = ai
        self._orchestrator = orchestrator
        self._max_question_length = max_question_length

    async def ask(
        self,
        question: str,
        *,
        sources: list[str] | None = None,
        client: Any = None,
        llm: LLMProvider | None = None,
    ) -> ResearchSession:
        cleaned = validate_question(question, max_length=self._max_question_length)
        logger.info("ask_start question=%r sources=%s", cleaned, sources or "all")

        started = time.perf_counter()
        outcome = await self._orchestrator.fetch(cleaned, sources=sources, client=client)

        if not outcome.sources:
            logger.error("no_sources question=%r failed=%s", cleaned, outcome.failed)
            raise ProviderError(
                f"no sources retrieved (failed: {', '.join(outcome.failed) or 'all'})"
            )

        answer = await self._ai.synthesize(cleaned, outcome.sources, llm=llm)
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "ask_done duration_ms=%d n_sources=%d n_citations=%d failed=%s",
            duration_ms, len(outcome.sources), len(answer.citations), outcome.failed,
        )

        return ResearchSession(
            question=cleaned,
            sources_used=outcome.sources,
            answer=answer,
            duration_ms=duration_ms,
            cache_hits={r.name: r.cache_hit for r in outcome.results},
            failed_sources=outcome.failed,
        )
