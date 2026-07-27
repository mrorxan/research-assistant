"""Run the five sample research questions live and save the results.

Writes one JSON record per question to artefacts/demo_run.json, including
timing, per-source cache state, and the cited answer. Requires a configured
.env with real API keys.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from researcher.cli import HTTP_USER_AGENT, build_researcher  # noqa: E402
from researcher.config import get_settings  # noqa: E402
from researcher.services.failover import build_llm  # noqa: E402

async def run_demo(question_limit: int, no_cache: bool) -> None:
    load_dotenv()
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    questions_file = ROOT / "data" / "research_questions.json"
    questions = json.loads(questions_file.read_text(encoding="utf-8"))["questions"]
    questions = questions[:question_limit]

    researcher = build_researcher(settings, bypass_cache=no_cache)
    llm = build_llm(settings)
    records: list[dict] = []

    async with httpx.AsyncClient(
        timeout=settings.per_source_timeout_seconds + 5,
        follow_redirects=True,
        headers={"User-Agent": HTTP_USER_AGENT},
    ) as client:
        for question in questions:
            print("=" * 60)
            print(f"Q[{question['id']}]: {question['text']}")
            started = time.perf_counter()
            try:
                session = await researcher.ask(question["text"], client=client, llm=llm)
            except Exception as exc:
                print(f"  failed: {exc}")
                records.append({"question_id": question["id"],
                                "question": question["text"], "error": str(exc)})
                continue
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            records.append({"question_id": question["id"],
                            "elapsed_ms": elapsed_ms, **session.to_dict()})
            print(f"  {elapsed_ms} ms, {len(session.sources_used)} sources, "
                  f"{len(session.answer.citations)} citations, "
                  f"failed={session.failed_sources or 'none'}")

    out_dir = ROOT / "artefacts"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "demo_run.json"
    out_file.write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nwrote {out_file.relative_to(ROOT)}")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5,
                        help="how many of the sample questions to run (default: 5)")
    parser.add_argument("--no-cache", action="store_true",
                        help="skip the cache: nothing is read or written")
    args = parser.parse_args()
    asyncio.run(run_demo(args.limit, args.no_cache))

if __name__ == "__main__":
    main()