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

## Run with Docker

```bash
docker build -t research-assistant .
docker run --rm --env-file .env research-assistant
docker run --rm --env-file .env research-assistant \
    python -m researcher ask "How does CRISPR-Cas9 work?" --sources wiki,arxiv
```

The image is a multi-stage build on `python:3.12.7-slim`: the build stage compiles
the dependency venv, the runtime stage ships only the venv and the source, and the
container runs as a non-root user.

## Tests

```bash
pytest                                          # full suite, all offline
pytest tests/test_ai_smoke.py -v                # provided smoke tests (contract)
pytest --cov=researcher --cov-report=term-missing
```

Current state, measured on Python 3.12.7:

- 92 tests passing: 76 of ours plus the 16 provided smoke tests.
- Coverage on `researcher/`: 96 percent.
- Every test runs offline. The `ai.*` boundary is monkeypatched; the network is never touched.
- `mypy` (strict-ish settings, 17 source files) and `ruff` both pass with zero findings.

## Sequential vs concurrent benchmark

```bash
python scripts/bench.py --N 5 --max-parallel 3
```

The benchmark replaces the fetchers with stubs that sleep 0.5 s each, so the
run is deterministic and measures the orchestrator itself rather than network
variance.

| Workload | N | Sequential | Concurrent (sem=3) | Speedup |
|---|---|---|---|---|
| 5 iterations x 3 sources, 0.5 s each | 5 | 7.589 s | 2.535 s | 2.99x |

The theoretical maximum with three equally slow sources is 3x, so the measured
2.99x shows the gather-based fan-out adds no meaningful overhead. In live runs
the bottleneck is the slowest source plus the LLM call: the full demo over the
five sample questions measured 3.6 to 5.1 s per question end to end
(see `artefacts/demo_run.json`).

## Live demo

```bash
python scripts/demo.py              # answers all 5 sample questions, saves artefacts/demo_run.json
python scripts/demo.py --limit 2
```

## Notes and limitations

- Wikipedia's search endpoint rejects clients without a descriptive User-Agent
  (HTTP 403), and matches article titles rather than full questions, so long
  questions can legitimately return zero Wikipedia sources. The pipeline
  degrades gracefully and says so in the output.
- Empty fetch results are not cached, so a source that had an outage is retried
  on the next ask instead of serving nothing for a whole TTL.
- The cache has no cross-process lock; two simultaneous asks for the same new
  question would both fetch live and the last writer wins. Entries are
  idempotent within their TTL, so this is harmless at CLI scale.
- Cost figures are estimates: the provided ai/ interface returns plain text,
  so token counts are approximated as characters divided by four.

## Tools and acknowledgements

The provided `ai/` package and the course LaTeX templates are the key external
inputs. AI assistance used during development is disclosed in the report and
the contribution statement.