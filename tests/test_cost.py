"""Cost telemetry: token estimation, JSONL persistence, summaries."""

from __future__ import annotations

import json
import time

from researcher.telemetry.cost import CostMeter, estimate_cost_usd, estimate_tokens


def test_estimate_tokens_rounds_up():
    assert estimate_tokens(0) == 0
    assert estimate_tokens(1) == 1
    assert estimate_tokens(4) == 1
    assert estimate_tokens(5) == 2
    assert estimate_tokens(400) == 100


def test_estimate_cost_uses_pricing_table():
    cost = estimate_cost_usd("gemini", "gemini-2.5-flash-lite", 1_000_000, 1_000_000)
    assert cost == 0.10 + 0.40


def test_estimate_cost_unknown_model_is_zero():
    assert estimate_cost_usd("acme", "mystery-model", 1000, 1000) == 0.0


def test_record_appends_jsonl(tmp_path):
    meter = CostMeter(tmp_path / "costs.jsonl")
    meter.record(provider="gemini", model="gemini-2.5-flash-lite", prompt_tokens=100, completion_tokens=50)
    meter.record(provider="gemini", model="gemini-2.5-flash-lite", prompt_tokens=200, completion_tokens=80)
    lines = (tmp_path / "costs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["prompt_tokens"] == 100
    assert first["cost_usd"] > 0


def test_read_since_filters_old_entries(tmp_path):
    path = tmp_path / "costs.jsonl"
    meter = CostMeter(path)
    old = {"timestamp": time.time() - 7200, "provider": "gemini", "model": "m",
           "prompt_tokens": 1, "completion_tokens": 1, "cost_usd": 0.0}
    path.write_text(json.dumps(old) + "\n", encoding="utf-8")
    meter.record(provider="gemini", model="m", prompt_tokens=2, completion_tokens=2)
    assert len(meter.read_since(1)) == 1
    assert len(meter.read_since(3)) == 2


def test_read_since_skips_corrupted_lines(tmp_path):
    path = tmp_path / "costs.jsonl"
    path.write_text("not json at all\n", encoding="utf-8")
    meter = CostMeter(path)
    meter.record(provider="gemini", model="m", prompt_tokens=1, completion_tokens=1)
    assert len(meter.read_since(1)) == 1


def test_summarise_groups_by_model(tmp_path):
    meter = CostMeter(tmp_path / "costs.jsonl")
    meter.record(provider="gemini", model="gemini-2.5-flash-lite", prompt_tokens=100, completion_tokens=50)
    meter.record(provider="gemini", model="gemini-2.5-flash-lite", prompt_tokens=100, completion_tokens=50)
    meter.record(provider="openai", model="gpt-4o-mini", prompt_tokens=10, completion_tokens=5)
    summary = meter.summarise(since_hours=1)
    assert summary["total_calls"] == 3
    assert summary["by_model"]["gemini/gemini-2.5-flash-lite"]["calls"] == 2
    assert summary["by_model"]["openai/gpt-4o-mini"]["prompt_tokens"] == 10


def test_missing_log_file_reads_empty(tmp_path):
    meter = CostMeter(tmp_path / "never_written.jsonl")
    assert meter.read_since(24) == []
    assert meter.summarise(24)["total_calls"] == 0
