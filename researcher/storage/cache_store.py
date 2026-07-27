"""Filesystem JSON cache with one file per (source, query) entry.

The store is deliberately dumb: it knows nothing about Source objects or
fetchers, it just persists JSON-serialisable values under a derived key and
answers whether a stored value is still within its TTL. What is worth caching
is decided one layer up, in the cache facade.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def canonicalise(query: str) -> str:
    """Normalise a query so casing and spacing variants share a cache key."""
    return " ".join(query.strip().lower().split())


def _digest(source: str, query: str) -> str:
    text = f"{source}::{canonicalise(query)}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


class CacheStore:
    def __init__(self, cache_dir: Path, ttl_seconds: int) -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._ttl = max(0, ttl_seconds)

    def _path(self, source: str, query: str) -> Path:
        return self._dir / f"{source}_{_digest(source, query)}.json"

    def get(self, source: str, query: str) -> Any | None:
        path = self._path(source, query)
        if not path.exists():
            return None
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("cache_read_failed path=%s error=%s", path, exc)
            return None
        stored_at = blob.get("stored_at", 0)
        age = time.time() - stored_at
        if age > self._ttl:
            logger.debug("cache_stale source=%s query=%r age_s=%.0f", source, query, age)
            return None
        logger.debug("cache_hit source=%s query=%r", source, query)
        return blob.get("value")

    def put(self, source: str, query: str, value: Any) -> None:
        path = self._path(source, query)
        payload = {"stored_at": time.time(), "value": value}
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            logger.debug("cache_write source=%s query=%r", source, query)
        except (OSError, TypeError) as exc:
            logger.warning("cache_write_failed path=%s error=%s", path, exc)

    def clear(self) -> int:
        removed = 0
        for file in self._dir.glob("*.json"):
            try:
                file.unlink()
                removed += 1
            except OSError as exc:
                logger.warning("cache_delete_failed path=%s error=%s", file, exc)
        return removed