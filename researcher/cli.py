"""Command line interface: ask, clear-cache, cost-report."""

from __future__ import annotations

import sys
import asyncio
import logging

import click
import httpx
from dotenv import load_dotenv

from ai.providers.base import ProviderError
from researcher.concurrency.orchestrator import ALL_SOURCES, SourceOrchestrator
from researcher.config import Settings, get_settings
from researcher.core.researcher import QuestionValidationError, Researcher
from researcher.models import ResearchSession
from researcher.services.ai_service import AIService
from researcher.services.cache import CachedAIService
from researcher.services.failover import build_llm
from researcher.storage.cache_store import CacheStore
from researcher.telemetry.cost import CostMeter

HTTP_USER_AGENT = (
    "ResearchAssistantBot/1.0 "
    "(https://github.com/mrorxan/research-assistant; mrorkhan.aiacademy@gmail.com) "
    "httpx/0.28"
)

def _configure_logging(level: str) -> None:
    # Windows consoles default to cp1252, which cannot print characters the
    # LLM likes to emit (arrows, em dashes). Reconfigure to UTF-8 up front.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

def _parse_sources(value: str | None) -> list[str] | None:
    if not value:
        return None
    chosen: list[str] = []
    for raw in value.split(","):
        name = raw.strip().lower()
        if name == "wiki":
            name = "wikipedia"
        if not name:
            continue
        if name not in ALL_SOURCES:
            raise click.UsageError(
                f"unknown source: {name!r}. Expected one of {', '.join(ALL_SOURCES)}."
            )
        if name not in chosen:
            chosen.append(name)
    return chosen or None

def _render(session: ResearchSession) -> str:
    lines = [f"Q: {session.question}", "", f"A: {session.answer.answer}", ""]
    if session.answer.citations:
        lines.append("References:")
        for citation in session.answer.citations:
            lines.append(f"  [{citation.index}] ({citation.source.origin}) {citation.source.title}")
            lines.append(f"      {citation.source.url}")
    if session.failed_sources:
        lines.append("")
        lines.append(f"(note: failed sources: {', '.join(session.failed_sources)})")
    lines.append("")
    cache_summary = ", ".join(
        f"{name}={'hit' if hit else 'miss'}" for name, hit in session.cache_hits.items()
    )
    lines.append(f"timings: {session.duration_ms} ms | cache: {cache_summary or 'n/a'}")
    return "\n".join(lines)

def build_researcher(settings: Settings, *, bypass_cache: bool) -> Researcher:
    meter = CostMeter(settings.cost_log_path)
    ai = AIService(settings, meter=meter)
    store = None if bypass_cache else CacheStore(settings.cache_dir, settings.cache_ttl_seconds)
    cached = CachedAIService(ai, store, bypass=bypass_cache)
    orchestrator = SourceOrchestrator(
        cached,
        per_source_timeout=settings.per_source_timeout_seconds,
        max_parallel=settings.max_parallel,
    )
    return Researcher(ai, orchestrator, max_question_length=settings.max_question_length)

async def _run_ask(question: str, sources: list[str] | None, no_cache: bool) -> ResearchSession:
    settings = get_settings()
    researcher = build_researcher(settings, bypass_cache=no_cache)
    llm = build_llm(settings)
    timeout = settings.per_source_timeout_seconds + 5
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": HTTP_USER_AGENT},
    ) as client:
        return await researcher.ask(question, sources=sources, client=client, llm=llm)

@click.group()
def cli() -> None:
    """Async Research Assistant."""
    load_dotenv()

@cli.command()
@click.argument("question")
@click.option(
    "--sources",
    default=None,
    help="Comma-separated subset of wiki,arxiv,web. Default: all three.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    help="Skip the cache entirely for this call: nothing is read or written.",
)
def ask(question: str, sources: str | None, no_cache: bool) -> None:
    """Answer QUESTION using Wikipedia, arXiv, and a web search in parallel."""
    settings = get_settings()
    _configure_logging(settings.log_level)
    try:
        chosen = _parse_sources(sources)
        session = asyncio.run(_run_ask(question, chosen, no_cache))
    except QuestionValidationError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(2)
    except ProviderError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(3)
    click.echo(_render(session))

@cli.command(name="clear-cache")
def clear_cache() -> None:
    """Delete every entry from the on-disk cache."""
    settings = get_settings()
    _configure_logging(settings.log_level)
    store = CacheStore(settings.cache_dir, settings.cache_ttl_seconds)
    removed = store.clear()
    click.echo(f"cleared {removed} cache entries from {settings.cache_dir}")

@cli.command(name="cost-report")
@click.option(
    "--since",
    default=24.0,
    show_default=True,
    help="Look-back window in hours.",
)
def cost_report(since: float) -> None:
    """Summarise estimated LLM spend recorded by previous ask calls."""
    settings = get_settings()
    _configure_logging(settings.log_level)
    summary = CostMeter(settings.cost_log_path).summarise(since_hours=since)
    click.echo(f"LLM cost report, last {since:g} h")
    click.echo(f"  calls: {summary['total_calls']}")
    click.echo(f"  estimated cost: ${summary['total_cost_usd']:.6f}")
    for model, bucket in summary["by_model"].items():
        click.echo(
            f"  {model}: {bucket['calls']} calls, "
            f"{bucket['prompt_tokens']} prompt + {bucket['completion_tokens']} completion tokens, "
            f"${bucket['cost_usd']:.6f}"
        )
    if summary["total_calls"] == 0:
        click.echo("  (no recorded calls in this window)")

if __name__ == "__main__":
    cli()