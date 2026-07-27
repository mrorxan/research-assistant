"""Cache-aware facade over AIService.

Each fetch consults the cache first and falls back to the live call. Empty
result lists are never cached: an empty answer usually means the source had a
bad day, and remembering that for a whole TTL would keep serving nothing
after the source recovers.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ai import Source, WebSearchProvider
from researcher.services.ai_service import AIService
from researcher.storage.cache_store import CacheStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchResult:
    sources: list[Source]
    cache_hit: bool


def _to_jsonable(sources: list[Source]) -> list[dict[str, Any]]:
    return [s.model_dump() for s in sources]


def _from_jsonable(payload: list[dict[str, Any]]) -> list[Source]:
    return [Source(**item) for item in payload]


class CachedAIService:
    def __init__(
        self,
        inner: AIService,
        store: CacheStore | None,
        *,
        bypass: bool = False,
    ) -> None:
        self._inner = inner
        self._store = store
        self._bypass = bypass

    async def _fetch(
        self,
        source: str,
        query: str,
        live: Callable[[], Awaitable[list[Source]]],
    ) -> FetchResult:
        if self._store is not None and not self._bypass:
            cached = self._store.get(source, query)
            if cached is not None:
                return FetchResult(sources=_from_jsonable(cached), cache_hit=True)
        result = await live()
        if self._store is not None and not self._bypass and result:
            self._store.put(source, query, _to_jsonable(result))
        return FetchResult(sources=result, cache_hit=False)

    async def fetch_wikipedia(self, query: str, *, client: Any = None) -> FetchResult:
        return await self._fetch(
            "wikipedia", query, lambda: self._inner.fetch_wikipedia(query, client=client)
        )

    async def fetch_arxiv(self, query: str, *, client: Any = None) -> FetchResult:
        return await self._fetch(
            "arxiv", query, lambda: self._inner.fetch_arxiv(query, client=client)
        )

    async def fetch_web(
        self,
        query: str,
        *,
        client: Any = None,
        provider: WebSearchProvider | None = None,
    ) -> FetchResult:
        return await self._fetch(
            "web", query, lambda: self._inner.fetch_web(query, client=client, provider=provider)
        )