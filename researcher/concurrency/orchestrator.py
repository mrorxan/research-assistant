"""Concurrent fan-out over the three sources with per-task isolation.

Each fetch runs as its own task inside its own asyncio.timeout window, so a
slow or failing source never blocks or cancels the others. Failures are
surfaced as structured SourceResult values instead of exceptions, which is
what lets the caller degrade gracefully.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ai import Source
from researcher.services.cache import CachedAIService, FetchResult

logger = logging.getLogger(__name__)

ALL_SOURCES: tuple[str, ...] = ("wikipedia", "arxiv", "web")

@dataclass(frozen=True)
class SourceResult:
    name: str
    sources: list[Source]
    error: str | None
    cache_hit: bool

@dataclass(frozen=True)
class FetchOutcome:
    sources: list[Source]
    results: list[SourceResult]
    failed: list[str]

class SourceOrchestrator:
    def __init__(
        self,
        service: CachedAIService,
        *,
        per_source_timeout: float,
        max_parallel: int,
    ) -> None:
        self._service = service
        self._timeout = per_source_timeout
        self._semaphore = asyncio.Semaphore(max_parallel)

    async def _run_one(
        self,
        name: str,
        fetch: Callable[[], Awaitable[FetchResult]],
    ) -> SourceResult:
        async with self._semaphore:
            try:
                async with asyncio.timeout(self._timeout):
                    result = await fetch()
            except TimeoutError:
                logger.warning("source_timeout name=%s timeout_s=%.1f", name, self._timeout)
                return SourceResult(name, [], "timeout", False)
            except Exception as exc:
                # Intentional per-source isolation: log the failure and surface
                # it as data so the remaining sources can still be used.
                logger.warning("source_failed name=%s error=%s", name, exc)
                return SourceResult(name, [], str(exc), False)
        return SourceResult(name, result.sources, None, result.cache_hit)

    async def fetch(
        self,
        query: str,
        *,
        sources: list[str] | None = None,
        client: Any = None,
    ) -> FetchOutcome:
        wanted = list(sources) if sources else list(ALL_SOURCES)
        fetchers: dict[str, Callable[[], Awaitable[FetchResult]]] = {
            "wikipedia": lambda: self._service.fetch_wikipedia(query, client=client),
            "arxiv": lambda: self._service.fetch_arxiv(query, client=client),
            "web": lambda: self._service.fetch_web(query, client=client),
        }
        tasks = [
            asyncio.create_task(self._run_one(name, fetchers[name]))
            for name in wanted
            if name in fetchers
        ]
        results = await asyncio.gather(*tasks)

        combined: list[Source] = []
        failed: list[str] = []
        for result in results:
            combined.extend(result.sources)
            if result.error is not None:
                failed.append(result.name)
        return FetchOutcome(sources=combined, results=list(results), failed=failed)
