# Contribution Statement

**Team:** Binary
**Topic:** Topic 4 — Async Research Assistant
**Repository:** https://github.com/mrorxan/research-assistant
**Final tag:** `v1.0-final`
**Submission date:** 2026-07-27

The project was split chronologically into two halves of comparable size. Orkhan
built the foundation and the service layer, everything from the project scaffold
up to and including the tested wrappers around the provided `ai/` package. At
that point the work was handed over, and Habil composed those pieces into the
concurrent application and shipped it: orchestration, business flow, CLI,
scripts, containerisation, and CI. Documentation was split the same way, each
member writing the sections that cover his own code.

---

## Member A — Orkhan Aliyev (`@mrorxan`)

**Owned (sole author of these files / PRs):**
- Project scaffold: provided `ai/`, `data/`, and smoke tests copied in unchanged; `.gitignore`, `.env.example`, `pytest.ini`, `requirements.txt`, initial `pyproject.toml`
- `researcher/config.py`
- `researcher/models.py`
- `researcher/storage/cache_store.py`
- `researcher/telemetry/cost.py`
- `researcher/services/ai_service.py`
- `researcher/services/cache.py`
- `tests/test_config.py`, `tests/test_models.py`, `tests/test_cache_store.py`, `tests/test_cost.py`, `tests/test_ai_service.py`, `tests/test_cache.py`
- SE-layer fixtures added to `tests/conftest.py` (the provided smoke-test fixtures kept unchanged above them)
- Report: Executive Summary, sections 1 (Overview), 2 (Architecture), 4 (Robustness), 5 (Storage & Caching)
- Slides 1–5 (title, problem, architecture, design decisions, service layer)
- README: quick start, CLI, environment variables, architecture, project layout sections

**Co-owned:**
- `tests/conftest.py` (provided fixtures + own additions, later reused by Habil's tests)

**Reviewed (PRs reviewed and approved):**
- All of Habil's pull requests: orchestrator, researcher flow and CLI, failover, scripts and artefacts, Docker and CI, and his documentation half.

**Approximate share of commits:** ~50 %

---

## Member B — Habil Huseynov (`@Habil7`)

**Owned (sole author of these files / PRs):**
- `researcher/concurrency/orchestrator.py`
- `researcher/core/researcher.py`
- `researcher/cli.py`, `researcher/__main__.py`
- `researcher/services/failover.py`
- `scripts/demo.py`, `scripts/bench.py`, and the committed run artefacts (`artefacts/bench.json`, `artefacts/demo_run.json`)
- `Dockerfile`, `.dockerignore`, `requirements-dev.txt`, `.github/workflows/ci.yml`
- ruff and mypy configuration in `pyproject.toml`
- `tests/test_orchestrator.py`, `tests/test_researcher.py`, `tests/test_cli.py`, `tests/test_end_to_end.py`, `tests/test_failover.py`
- `docs/architecture.md`
- Report: sections 3 (Concurrency & Performance), 6 (Testing), 7 (Deployment), 8 (Bonus Features), 9 (Limitations & Future Work), Tools & Acknowledgements, Appendix
- Slides 6–10 (benchmark, robustness, sample run, testing, limitations)
- README: Docker, tests, benchmark, live demo, limitations, tools sections

**Co-owned:**
- `tests/conftest.py` (consumer of the shared fixtures; extended none)

**Reviewed (PRs reviewed and approved):**
- All of Orkhan's pull requests: scaffold, config and models, cache store and telemetry, service layer, and his documentation half.

**Approximate share of commits:** ~50 %

---

## AI tool disclosure (also in the report, Tools & Acknowledgements)

We used Claude (Anthropic) as an AI coding assistant throughout, as the course
brief permits: as a collaborator, not a ghostwriter. The table lists the
substantial uses.

| Module / area | Assistant | What the team did with it |
|---|---|---|
| SE-layer modules (`researcher/`) | Claude | Drafted against the architecture and policies we specified; every file reviewed, adjusted, and verified by running the suite and live calls before commit. |
| Test suite | Claude | Drafted test cases per module; the team reviewed each, kept what pinned real behaviour, and validated the suite offline and inside Docker. |
| Report, slides, README | Claude | Drafted from our measured results; every number cross-checked against the committed artefacts (`bench.json`, `demo_run.json`, coverage output). |
| Debugging live incidents | Claude | Helped diagnose the Wikipedia User-Agent 403 policy and the Windows cp1252 console crash; fixes were tested live. |

Every measured figure in the deliverables comes from runs executed by the team
on the submission machine. Each module has a primary owner listed above who can
walk through and defend it.

---

## Signatures

By signing below, we affirm that:
- The contributions described above are accurate.
- The commit shares reflect actual work, not artificially split commits.
- Each module has a primary owner who understands and can explain it.
- AI assistant usage has been disclosed as described above.

| Member | Signature | Date |
|---|---|---|
| Orkhan Aliyev | __________________________ | __________ |
| Habil Huseynov | __________________________ | __________ |