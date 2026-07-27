"""Retry, timeout, logging, and cost wrapper around the provided ai.* calls.

Every call from the rest of the codebase into the ai/ package goes through
this module, so the cross-cutting policies live in exactly one place.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from tenacity import (
    AsyncRetrying,
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ai import (
    AnswerWithCitations,
    Source,
    WebSearchProvider,
    fetch_arxiv,
    fetch_web,
    fetch_wikipedia,
    synthesize,
)
from ai.providers.base import LLMProvider, ProviderError
from researcher.config import Settings
from researcher.telemetry.cost import CostMeter, estimate_tokens

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self, settings: Settings, *, meter: CostMeter | None = None) -> None:
        self._settings = settings
        self._meter = meter

    def _async_retrying(self) -> AsyncRetrying:
        s = self._settings
        return AsyncRetrying(
            stop=stop_after_attempt(s.retry_max_attempts),
            wait=wait_exponential(multiplier=s.retry_backoff_min, max=s.retry_backoff_max),
            retry=retry_if_exception_type(ProviderError),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

    def _sync_retrying(self) -> Retrying:
        s = self._settings
        return Retrying(
            stop=stop_after_attempt(s.retry_max_attempts),
            wait=wait_exponential(multiplier=s.retry_backoff_min, max=s.retry_backoff_max),
            retry=retry_if_exception_type(ProviderError),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

    async def fetch_wikipedia(self, query: str, *, client: Any = None) -> list[Source]:
        async for attempt in self._async_retrying():
            with attempt:
                logger.info("fetch_start source=wikipedia query=%r", query)
                result = await fetch_wikipedia(
                    query, max_results=self._settings.max_sources_per_query, client=client
                )
                logger.info("fetch_done source=wikipedia query=%r n=%d", query, len(result))
                return result
        raise ProviderError("wikipedia retry loop exhausted")

    async def fetch_arxiv(self, query: str, *, client: Any = None) -> list[Source]:
        async for attempt in self._async_retrying():
            with attempt:
                logger.info("fetch_start source=arxiv query=%r", query)
                result = await fetch_arxiv(
                    query, max_results=self._settings.max_sources_per_query, client=client
                )
                logger.info("fetch_done source=arxiv query=%r n=%d", query, len(result))
                return result
        raise ProviderError("arxiv retry loop exhausted")

    async def fetch_web(
        self,
        query: str,
        *,
        client: Any = None,
        provider: WebSearchProvider | None = None,
    ) -> list[Source]:
        async for attempt in self._async_retrying():
            with attempt:
                logger.info("fetch_start source=web query=%r", query)
                result = await fetch_web(
                    query,
                    max_results=self._settings.max_sources_per_query,
                    provider=provider,
                    client=client,
                )
                logger.info("fetch_done source=web query=%r n=%d", query, len(result))
                return result
        raise ProviderError("web retry loop exhausted")

    async def synthesize(
        self,
        question: str,
        sources: list[Source],
        *,
        llm: LLMProvider | None = None,
    ) -> AnswerWithCitations:
        """Run the blocking ai.synthesize in a worker thread, with retries and a timeout.

        If the timeout fires, the awaiting caller is released but the worker
        thread cannot be killed and finishes in the background. That is an
        accepted trade-off for a short-lived CLI process.
        """

        def _call() -> AnswerWithCitations:
            for attempt in self._sync_retrying():
                with attempt:
                    return synthesize(question, sources, llm=llm)
            raise ProviderError("synthesize retry loop exhausted")

        timeout = self._settings.synthesize_timeout_seconds
        logger.info("synthesize_start n_sources=%d", len(sources))
        try:
            answer = await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout)
        except TimeoutError:
            logger.warning("synthesize_timeout timeout_s=%.1f", timeout)
            raise ProviderError(f"synthesize timed out after {timeout:.0f}s") from None
        logger.info("synthesize_done n_citations=%d", len(answer.citations))
        self._record_cost(question, sources, answer)
        return answer

    def _record_cost(
        self, question: str, sources: list[Source], answer: AnswerWithCitations
    ) -> None:
        if self._meter is None:
            return
        prompt_chars = len(question) + sum(
            len(s.title) + len(s.url) + min(len(s.snippet), 600) for s in sources
        ) + 300
        self._meter.record(
            provider=self._settings.llm_provider,
            model=self._settings.llm_model,
            prompt_tokens=estimate_tokens(prompt_chars),
            completion_tokens=estimate_tokens(len(answer.answer)),
        )