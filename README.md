# Async Research Assistant

> Ask a research question; the system queries Wikipedia, arXiv, and a web search in parallel, then synthesises one cited answer with an LLM.

**Team:** Binary • **Topic:** 4 • **Course:** AI-ENG-110 Software Engineering, AI Academy

## Quick start

```bash
git clone https://github.com/mrorxan/research-assistant.git
cd research-assistant
python -m venv .venv
.venv\Scripts\activate            # Windows; on Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env              # then fill in GOOGLE_API_KEY and TAVILY_API_KEY
python -m researcher ask "What is photosynthesis and what are its main stages?"
```

The default provider stack is Gemini 2.5 Flash Lite (free tier on Google AI Studio)
for synthesis and Tavily (free tier, 1000 requests per month) for web search.
Wikipedia and arXiv need no keys. Anthropic or OpenAI can be swapped in through
`LLM_PROVIDER` and `LLM_MODEL` without touching any code.

## CLI

```bash
python -m researcher ask "How does CRISPR-Cas9 work?"               # all three sources
python -m researcher ask "..." --sources wiki,arxiv                 # subset
python -m researcher ask "..." --no-cache                           # skip cache entirely
python -m researcher clear-cache                                    # wipe the on-disk cache
python -m researcher cost-report --since 24                         # estimated LLM spend
```

Exit codes: `0` success, `2` invalid question (empty or over the length limit),
`3` provider failure (for example, every source failed).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` | `gemini` / `gemini-2.5-flash-lite` | LLM used by `ai.synthesize`. |
| `GOOGLE_API_KEY` (or `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) | — | Key for the chosen LLM provider. |
| `LLM_FALLBACK_PROVIDER` / `LLM_FALLBACK_MODEL` | empty | Optional failover: retry a failed LLM call against a second provider. |
| `WEB_SEARCH_PROVIDER` | `tavily` | `tavily`, `serper`, or `duckduckgo`. |
| `TAVILY_API_KEY` / `SERPER_API_KEY` | — | Key for the chosen web search provider. |
| `LOG_LEVEL` | `INFO` | Logging level for the whole app. |
| `CACHE_DIR` / `CACHE_TTL_SECONDS` | `./.cache` / `86400` | On-disk JSON cache location and lifetime. |
| `COST_LOG_PATH` | `./.cache/costs.jsonl` | Where LLM cost records are appended. |
| `PER_SOURCE_TIMEOUT_SECONDS` | `15` | Timeout for each source fetch. |
| `SYNTHESIZE_TIMEOUT_SECONDS` | `60` | Timeout for the LLM synthesis call. |
| `MAX_SOURCES_PER_QUERY` | `3` | Results requested per source. |
| `MAX_PARALLEL` | `3` | Semaphore bound on concurrent fetches. |
| `MAX_QUESTION_LENGTH` | `500` | Longer questions are rejected with exit code 2. |
| `RETRY_MAX_ATTEMPTS` / `RETRY_BACKOFF_MIN` / `RETRY_BACKOFF_MAX` | `3` / `1.0` / `8.0` | Tenacity retry policy for every `ai.*` call. |

An invalid value (for example `LOG_LEVEL=chatty` or `MAX_PARALLEL=0`) fails at
startup with a pydantic validation error naming the field. A missing API key
surfaces at the first provider call as a `ProviderError`.

## Architecture

```
+---------+
|   CLI   |  python -m researcher (ask, clear-cache, cost-report)
+----+----+
     |
     v
+---------------+      +----------------------+
|  Researcher   +----->+  SourceOrchestrator  |  asyncio.gather, semaphore,
| (validation)  |      |                      |  per-task timeout, isolation
+-------+-------+      +----------+-----------+
        |                         |
        |                         v
        |              +----------+-----------+       +----------------+
        |              |   CachedAIService    +------>+   CacheStore   |
        |              | (hit/miss, serialise)|       | (FS JSON, TTL) |
        |              +----------+-----------+       +----------------+
        |                         |
        v                         v
+-------+-------------------------+------+
|               AIService                |  tenacity retries, timeouts,
|  (the only module that imports ai.*)   |  structured logs, cost records
+-------------------+--------------------+
                    |
                    v
        +-----------+-----------+
        |    ai/  (provided)    |  fetch_wikipedia / fetch_arxiv /
        |      unchanged        |  fetch_web / synthesize
        +-----------------------+
```

`Researcher` talks to `AIService` directly only for the synthesis step; every
source fetch goes through the orchestrator and the cache facade. Details and
the reasoning behind each boundary are in [docs/architecture.md](docs/architecture.md).

## Project layout

```
.
+-- ai/                        provided AI module, copied unchanged
+-- researcher/
|   +-- config.py              env -> typed Settings (pydantic-settings)
|   +-- models.py              ResearchSession
|   +-- cli.py                 click commands and output rendering
|   +-- core/researcher.py     validate -> fetch -> synthesise -> package
|   +-- concurrency/orchestrator.py
|   +-- services/ai_service.py retry + timeout + log wrapper around ai.*
|   +-- services/cache.py      cache facade (never caches empty results)
|   +-- services/failover.py   optional multi-provider LLM failover
|   +-- storage/cache_store.py filesystem JSON cache with TTL
|   +-- telemetry/cost.py      estimated cost records + summaries
+-- tests/                     our tests + the provided smoke tests
+-- scripts/                   demo.py (live) and bench.py (deterministic)
+-- data/                      5 sample research questions
+-- artefacts/                 outputs of real runs (bench.json, demo_run.json)
+-- Dockerfile, requirements.txt, .env.example, pyproject.toml
```

<!-- HABIL-HISSESI: Docker, Tests, Benchmark, Live demo, Notes, Tools bolmeleri PR-12-de buraya elave olunacaq -->