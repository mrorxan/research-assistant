# Architecture

## One-line summary

A CLI takes a question, the orchestrator fetches Wikipedia, arXiv, and a web
search concurrently with per-source timeouts and a TTL cache, then the LLM
synthesises one answer with numbered citations.

## Layers and responsibilities

```
researcher/cli.py            click commands, logging setup, output rendering
researcher/core/researcher.py    validate the question, run the flow, package ResearchSession
researcher/concurrency/orchestrator.py   asyncio.gather fan-out, semaphore, per-task timeout, isolation
researcher/services/cache.py     cache facade: read cache, fall back to live, never store empty
researcher/services/ai_service.py    retries, synthesize timeout, structured logs, cost records
researcher/services/failover.py      optional FailoverLLM chain for the synthesis step
researcher/storage/cache_store.py    filesystem JSON persistence with TTL
researcher/telemetry/cost.py         JSONL cost records and summaries
ai/                              provided, unchanged
```

## Key boundaries

1. The ai/ boundary. Only `services/ai_service.py` imports the `ai` package.
   Everything above it deals with our own types, so swapping the LLM provider
   is an environment variable change, not a code change.
2. The storage boundary. `CacheStore` only understands strings and JSON.
   Serialising `Source` objects to JSON and back lives in the cache facade,
   so the store can later be replaced by Postgres or Redis behind the same
   get/put interface.
3. The concurrency boundary. Only `SourceOrchestrator` creates tasks and
   calls `asyncio.gather`. Below it everything is a plain awaited call.

## Data flow for one ask

question string
-> `Researcher.ask` validates (non-empty, length cap)
-> `SourceOrchestrator.fetch` starts one task per requested source
-> each task: semaphore slot -> `asyncio.timeout` window -> `CachedAIService.fetch_*`
-> cache hit returns immediately; miss goes to `AIService.fetch_*`
-> `AIService` retries transient `ProviderError`s with exponential backoff
-> `ai.fetch_*` performs the HTTP call using the shared client
-> results come back as structured `SourceResult`s (data, not exceptions)
-> combined sources go to `AIService.synthesize` (thread + retry + timeout)
-> `ai.synthesize` prompts the LLM and filters hallucinated citation indices
-> `Researcher` packages everything into a `ResearchSession`
-> the CLI renders answer, references, failed-source note, timing, cache state

## Design decisions and their reasons

- asyncio over threads or processes. The work is three I/O-bound HTTP calls;
  one event loop handles them with minimal overhead, and the provided fetchers
  are already coroutines. Threads add scheduling cost without parallel gain
  under the GIL; process pools are for CPU-bound work.
- Per-task `asyncio.timeout` instead of one timeout around the gather. A slow
  Wikipedia response must not consume arXiv's window or cancel completed work.
  A timed-out task becomes `SourceResult(error="timeout")` and the rest of the
  pipeline continues.
- Structured results instead of `return_exceptions=True`. We want to know per
  source whether it failed, why, and whether it was a cache hit, so every task
  returns a `SourceResult` value and the gather never sees an exception.
- Empty results are not cached. An empty list usually means the source was
  briefly unhappy (or the question simply does not match an article title).
  Caching it would freeze that bad state for a whole TTL.
- Filesystem JSON cache rather than PostgreSQL. TOPIC.md explicitly allows it,
  entries are idempotent within their TTL so ACID adds nothing here, and a
  JSON file on disk can be inspected directly while debugging.
- A timeout on synthesize as well. The fetches always had timeouts; without
  one on the LLM call a hung provider would hang the CLI forever. The call
  runs in a worker thread bounded by `asyncio.wait_for`; on timeout the user
  gets a clean `ProviderError` (exit code 3). The abandoned thread finishes
  in the background, which is acceptable for a short-lived CLI process.
- Cache hit information travels in the return value (`FetchResult`), not in
  shared mutable state, so concurrent asks against one service object cannot
  interleave their bookkeeping.
- A Wikipedia-policy-compliant User-Agent on the shared httpx client. During
  development Wikipedia returned HTTP 403 for the default and for
  browser-imitating agents; their API policy requires an identifying agent
  with contact information. The shared client also reuses connections across
  all three fetchers.

## OOP shape

The provided `ai/providers/base.py` shows the inheritance pattern (abstract
`LLMProvider` with three concrete subclasses picked by a factory). Our own
`FailoverLLM` subclasses that same ABC, which is what lets `ai.synthesize`
accept it without the ai/ package knowing failover exists. Everywhere else we
use composition: `CachedAIService` holds an `AIService` and a `CacheStore`;
`SourceOrchestrator` holds the cached service; `Researcher` holds the
orchestrator and the AI service. We did not add new ABCs of our own because
each role has exactly one implementation at runtime; the failover chain is
the place where polymorphism actually earns its keep.