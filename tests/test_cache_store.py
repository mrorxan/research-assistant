"""CacheStore: put/get round trip, TTL expiry, canonicalisation, clear."""

from __future__ import annotations

import time

from researcher.storage.cache_store import CacheStore, canonicalise


def test_put_then_get_returns_value(tmp_path):
    store = CacheStore(tmp_path, ttl_seconds=60)
    store.put("wikipedia", "photosynthesis", [{"title": "x"}])
    assert store.get("wikipedia", "photosynthesis") == [{"title": "x"}]


def test_missing_key_returns_none(tmp_path):
    store = CacheStore(tmp_path, ttl_seconds=60)
    assert store.get("wikipedia", "never asked") is None


def test_expired_entry_returns_none(tmp_path):
    store = CacheStore(tmp_path, ttl_seconds=0)
    store.put("arxiv", "q", [1, 2])
    time.sleep(0.01)
    assert store.get("arxiv", "q") is None


def test_equivalent_queries_share_a_key(tmp_path):
    store = CacheStore(tmp_path, ttl_seconds=60)
    store.put("web", "What is Photosynthesis?", ["one"])
    assert store.get("web", "  what is photosynthesis?  ") == ["one"]
    assert store.get("web", "WHAT  IS PHOTOSYNTHESIS?") == ["one"]


def test_sources_have_separate_keys(tmp_path):
    store = CacheStore(tmp_path, ttl_seconds=60)
    store.put("wikipedia", "q", ["wiki"])
    store.put("arxiv", "q", ["arxiv"])
    assert store.get("wikipedia", "q") == ["wiki"]
    assert store.get("arxiv", "q") == ["arxiv"]


def test_clear_removes_every_entry(tmp_path):
    store = CacheStore(tmp_path, ttl_seconds=60)
    store.put("wikipedia", "q1", [1])
    store.put("arxiv", "q2", [2])
    assert store.clear() == 2
    assert store.get("wikipedia", "q1") is None
    assert store.get("arxiv", "q2") is None


def test_corrupted_file_counts_as_miss(tmp_path):
    store = CacheStore(tmp_path, ttl_seconds=60)
    store._path("web", "q").write_text("this is not json{{", encoding="utf-8")
    assert store.get("web", "q") is None


def test_canonicalise_trims_and_collapses_whitespace():
    assert canonicalise("  HELLO   world  ") == "hello world"