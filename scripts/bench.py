"""Sequential versus concurrent benchmark for the source-fetching step.

Uses stub fetchers that sleep a fixed amount instead of hitting the network,
so the run is deterministic and isolates the orchestrator's own overhead
from provider variance. Results are printed and saved to artefacts/bench.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai.schemas import Source  # noqa: E402
from researcher.concurrency.orchestrator import SourceOrchestrator  # noqa: E402
from researcher.services.cache import FetchResult  # noqa: E402

SLEEP_PER_SOURCE_S = 0.5

class SleepingService:
    """Stands in for CachedAIService: each fetch sleeps, then returns one Source."""

    async def _one(self, name: str) -> FetchResult:
        await asyncio.sleep(SLEEP_PER_SOURCE_S)
        source = Source(
            title=f"{name} result",
            url=f"https://example.org/{name}",
            snippet=f"{name} snippet",
            origin=name,
        )
        return FetchResult(sources=[source], cache_hit=False)

    async def fetch_wikipedia(self, query, *, client=None) -> FetchResult:
        return await self._one("wikipedia")

    async def fetch_arxiv(self, query, *, client=None) -> FetchResult:
        return await self._one("arxiv")

    async def fetch_web(self, query, *, client=None, provider=None) -> FetchResult:
        return await self._one("web")

async def run_sequential(service: SleepingService, iterations: int) -> float:
    started = time.perf_counter()
    for _ in range(iterations):
        await service.fetch_wikipedia("q")
        await service.fetch_arxiv("q")
        await service.fetch_web("q")
    return time.perf_counter() - started

async def run_concurrent(service: SleepingService, iterations: int, max_parallel: int) -> float:
    orchestrator = SourceOrchestrator(
        service, per_source_timeout=10.0, max_parallel=max_parallel
    )
    started = time.perf_counter()
    for _ in range(iterations):
        await orchestrator.fetch("q")
    return time.perf_counter() - started


async def run_benchmark(iterations: int, max_parallel: int) -> None:
    service = SleepingService()
    sequential = await run_sequential(service, iterations)
    concurrent = await run_concurrent(service, iterations, max_parallel)
    result = {
        "n_iterations": iterations,
        "sleep_per_source_s": SLEEP_PER_SOURCE_S,
        "max_parallel": max_parallel,
        "sequential_s": round(sequential, 3),
        "concurrent_s": round(concurrent, 3),
        "speedup": round(sequential / concurrent, 2) if concurrent > 0 else None,
    }
    print(json.dumps(result, indent=2))
    out_dir = ROOT / "artefacts"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "bench.json"
    out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {out_file.relative_to(ROOT)}")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--N", type=int, default=5,
                        help="how many iterations to benchmark (default: 5)")
    parser.add_argument("--max-parallel", type=int, default=3,
                        help="semaphore bound for the concurrent run (default: 3)")
    args = parser.parse_args()
    asyncio.run(run_benchmark(args.N, args.max_parallel))

if __name__ == "__main__":
    main()