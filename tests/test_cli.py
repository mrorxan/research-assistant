"""CLI: parsing, rendering, exit codes, cost-report output."""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from ai.providers.base import ProviderError
from ai.schemas import AnswerWithCitations, Citation, Source
from researcher import cli as cli_module
from researcher.core.researcher import QuestionValidationError
from researcher.models import ResearchSession

def _fake_session() -> ResearchSession:
    source = Source(
        title="Photosynthesis",
        url="https://en.wikipedia.org/wiki/Photosynthesis",
        snippet="snippet",
        origin="wikipedia",
    )
    answer = AnswerWithCitations(
        question="Q",
        answer="Light becomes chemical energy [1].",
        citations=[Citation(index=1, source=source)],
    )
    return ResearchSession(
        question="Q",
        sources_used=[source],
        answer=answer,
        duration_ms=42,
        cache_hits={"wikipedia": False, "arxiv": True, "web": False},
        failed_sources=[],
    )

def test_parse_sources_maps_wiki_alias():
    assert cli_module._parse_sources("wiki,arxiv") == ["wikipedia", "arxiv"]

def test_parse_sources_rejects_unknown():
    with pytest.raises(click.UsageError):
        cli_module._parse_sources("reddit")

def test_parse_sources_empty_means_all():
    assert cli_module._parse_sources("") is None
    assert cli_module._parse_sources(None) is None

def test_parse_sources_dedupes():
    assert cli_module._parse_sources("wiki,wikipedia,arxiv") == ["wikipedia", "arxiv"]

def test_render_shows_citations_cache_and_timing():
    text = cli_module._render(_fake_session())
    assert "Q: Q" in text
    assert "[1] (wikipedia) Photosynthesis" in text
    assert "timings: 42 ms" in text
    assert "arxiv=hit" in text

def test_render_notes_failed_sources():
    session = _fake_session().model_copy(update={"failed_sources": ["arxiv"]})
    assert "failed sources: arxiv" in cli_module._render(session)

def test_ask_prints_answer(monkeypatch):
    async def fake_run(question, sources, no_cache):
        assert question == "What is X?"
        return _fake_session()

    monkeypatch.setattr(cli_module, "_run_ask", fake_run)
    result = CliRunner().invoke(cli_module.cli, ["ask", "What is X?"])
    assert result.exit_code == 0
    assert "Light becomes chemical energy" in result.output

def test_ask_validation_error_exits_2(monkeypatch):
    async def fake_run(question, sources, no_cache):
        raise QuestionValidationError("empty")

    monkeypatch.setattr(cli_module, "_run_ask", fake_run)
    result = CliRunner().invoke(cli_module.cli, ["ask", "   "])
    assert result.exit_code == 2
    assert "error: empty" in result.output

def test_ask_provider_error_exits_3(monkeypatch):
    async def fake_run(question, sources, no_cache):
        raise ProviderError("all sources down")

    monkeypatch.setattr(cli_module, "_run_ask", fake_run)
    result = CliRunner().invoke(cli_module.cli, ["ask", "x"])
    assert result.exit_code == 3
    assert "all sources down" in result.output

def test_clear_cache_command(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    cli_module.get_settings.cache_clear()
    result = CliRunner().invoke(cli_module.cli, ["clear-cache"])
    cli_module.get_settings.cache_clear()
    assert result.exit_code == 0
    assert "cleared" in result.output

def test_cost_report_empty_window(tmp_path, monkeypatch):
    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "costs.jsonl"))
    cli_module.get_settings.cache_clear()
    result = CliRunner().invoke(cli_module.cli, ["cost-report", "--since", "2"])
    cli_module.get_settings.cache_clear()
    assert result.exit_code == 0
    assert "no recorded calls" in result.output

def test_cost_report_shows_totals(tmp_path, monkeypatch):
    from researcher.telemetry.cost import CostMeter

    log = tmp_path / "costs.jsonl"
    CostMeter(log).record(
        provider="gemini", model="gemini-2.5-flash-lite",
        prompt_tokens=100, completion_tokens=50,
    )
    monkeypatch.setenv("COST_LOG_PATH", str(log))
    cli_module.get_settings.cache_clear()
    result = CliRunner().invoke(cli_module.cli, ["cost-report"])
    cli_module.get_settings.cache_clear()
    assert result.exit_code == 0
    assert "calls: 1" in result.output
    assert "gemini/gemini-2.5-flash-lite" in result.output