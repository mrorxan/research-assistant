"""Cost telemetry for LLM calls.

The provided ai/ package returns plain text, so exact token counts from the
provider response are not available to the SE layer. We estimate tokens as
ceil(characters / 4), which is the common rule of thumb for English text, and
we say so in the report. Records are appended to a JSONL file so the
cost-report CLI command can summarise spend later.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PRICING_USD_PER_1M_TOKENS: dict[tuple[str, str], tuple[float, float]] = {
    ("gemini", "gemini-2.5-flash-lite"): (0.10, 0.40),
    ("gemini", "gemini-2.0-flash"): (0.10, 0.40),
    ("anthropic", "claude-sonnet-4-6"): (3.00, 15.00),
    ("anthropic", "claude-3-5-haiku-20241022"): (0.80, 4.00),
    ("openai", "gpt-4o-mini"): (0.15, 0.60),
}


def estimate_tokens(char_count: int) -> int:
    """Rough token estimate for English text: about 4 characters per token."""
    if char_count <= 0:
        return 0
    return math.ceil(char_count / 4)


def estimate_cost_usd(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prompt_price, completion_price = PRICING_USD_PER_1M_TOKENS.get((provider, model), (0.0, 0.0))
    return (prompt_tokens / 1_000_000) * prompt_price + (completion_tokens / 1_000_000) * completion_price


class CostMeter:
    """Appends one JSONL record per LLM call and summarises them on demand."""

    def __init__(self, log_path: Path) -> None:
        self._path = Path(log_path)

    def record(self, *, provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> dict[str, Any]:
        entry = {
            "timestamp": time.time(),
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": round(estimate_cost_usd(provider, model, prompt_tokens, completion_tokens), 8),
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        except OSError as exc:
            logger.warning("cost_record_failed path=%s error=%s", self._path, exc)
        return entry

    def read_since(self, since_hours: float) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        cutoff = time.time() - since_hours * 3600
        entries: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("cost_record_corrupted line=%r", line[:80])
                continue
            if entry.get("timestamp", 0) >= cutoff:
                entries.append(entry)
        return entries

    def summarise(self, since_hours: float) -> dict[str, Any]:
        entries = self.read_since(since_hours)
        by_model: dict[str, dict[str, Any]] = {}
        for entry in entries:
            key = f"{entry.get('provider')}/{entry.get('model')}"
            bucket = by_model.setdefault(
                key, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
            )
            bucket["calls"] += 1
            bucket["prompt_tokens"] += entry.get("prompt_tokens", 0)
            bucket["completion_tokens"] += entry.get("completion_tokens", 0)
            bucket["cost_usd"] += entry.get("cost_usd", 0.0)
        return {
            "since_hours": since_hours,
            "total_calls": len(entries),
            "total_cost_usd": round(sum(e.get("cost_usd", 0.0) for e in entries), 8),
            "by_model": by_model,
        }
