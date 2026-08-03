# ScanFlow AI — live progress

**Read this file first in any new session.** It's the up-to-date status; the
unchanging rationale/plan is in `agent/PLAN.md`. If you're a fresh agent with
no memory of this conversation: read this file, then `agent/PLAN.md`, then
`plan.md` (original 21-step spec) and `DATA_SOURCES.md` /
`docs/data_dictionary.md` before touching code.

Last updated: 2026-08-03 (mid-session).

## TL;DR current state

- **Milestone 1 (Foundation): done and verified.**
- **Milestone 2 (Reliable ingestion): done and verified — including a real
  Kestra execution, not just unit tests.**
- **Milestone 3 (Analytics vertical slice): done and verified — real
  derived metrics, real analytical tools, a working (if minimal) Streamlit
  app, all checked against real NHS numbers.**
- The old arXiv-project code has been removed (not just left unused) — see
  "arXiv cleanup" below.
- Everything marked done here is tested against real data/a real running
  system, not aspirational.

## Infra notes (resolved, but worth knowing)

- Earlier full-disk incident (see git history / prior conversation) corrupted
  the `app_postgres` volume; it was recreated and all NHS data reloaded.
  Resolved, not a live issue.
- **Found and fixed a real, pre-existing bug**: both Kestra flow YAMLs used
  `type: io.kestra.plugin.core.runner.Docker`, which doesn't exist in this
  Kestra distribution (v1.3.21) — the real type is
  `io.kestra.plugin.scripts.runner.docker.Docker`. Confirmed via the
  `/api/v1/plugins` endpoint, not guessed.
- **Found and fixed a second real bug**: the Dockerfile had no
  `.dockerignore`, so `COPY . .` copied the *host's own* `.venv` (with
  symlinks to `/Users/yessinezghal/miniconda3/...`) on top of the correctly
  built container `.venv`, breaking `python` entirely inside the image. Fixed
  with `.dockerignore` (excludes `.venv/`, `.git/`, `agent/`, caches, etc.).
  This bug would have affected the app container generally, not just Kestra.
- Both fixes verified by actually triggering `ingest_diagnostics` in a live
  Kestra instance via its REST API (`curl -u admin@kestra.io:Admin1234! ...`)
  and confirming `SUCCESS` with real log output (discovered URLs, correct
  idempotent skips).
- Browser automation (`mcp__claude-in-chrome`) was disconnected when testing
  the new Streamlit app — verified instead via direct Python calls against
  real data (see Milestone 3) and an HTTP 200 page load. If you're a fresh
  session and the browser tools work, a real click-through of the Streamlit
  app is still worth doing as a first check.

## arXiv cleanup (done, per explicit user request)

Removed entirely (no reuse value): `ingest/arxiv_source.py`,
`ingest/pipeline.py` (arXiv dlt pipeline), `rag/agent.py` (arXiv-specific
tool-calling agent), `flows/ingest_arxiv.yaml`, `data/raw/papers.jsonl`,
`data/eval/{ground_truth,rag_eval_results,retrieval_eval_results}.csv`,
`data/arxiv_ingest.duckdb`, `data/embeddings_cache.npz`.

Kept (generic, reusable infrastructure, not arXiv-specific): `search/*`
(minsearch/ES/rerank/retriever — operates on generic `list[dict]` docs),
`db/*` (SQLAlchemy pattern + monitoring tables), `eval/*` (generic
evaluation scripts, will be repointed at the NHS RAG corpus in Milestone 4),
`rag/pipeline.py`/`prompts.py`/`query_rewrite.py` (generic RAG pipeline
pattern, will be repointed in Milestone 4, currently unused/dormant).

`config.py`: removed `ARXIV_CATEGORIES`/`ARXIV_TOPICS`/`ARXIV_MAX_RESULTS_PER_TOPIC`
(dead now). Renamed defaults: `RAW_DOCS_PATH` now points at
`data/raw/documents.jsonl` (not `papers.jsonl`), `ELASTIC_INDEX_NAME` default
now `scanflow-documents` (not `arxiv-papers`) — updated in `.env`,
`.env.example`, `docker-compose.yml` too.

`agent/` folder itself is now gitignored (per user request) — it's working
scaffolding for session continuity, not meant to ship in the submitted repo.

**`README.md` is still the old arXiv-project version** — stale, not yet
rewritten. Deliberately deferred to Milestone 8 (final docs pass); don't be
confused by it in the meantime.

## Milestone 1 — Foundation ✅ DONE

See prior detail below (unchanged): `DATA_SOURCES.md`, `docs/data_dictionary.md`,
`database/schema.sql` + `src/llm_project/db/nhs_schema.py`, 3 real months loaded
(464 providers, 5,480 waiting/activity facts, 853 CDC facts), all constraint
checks verified.

## Milestone 2 — Reliable ingestion ✅ DONE

- `src/llm_project/ingest/nhs_source.py`, `nhs_pipeline.py`, `nhs_discover.py`,
  `nhs_discovered_run.py` — deterministic, idempotent, self-discovering.
- `flows/ingest_diagnostics.yaml` — **verified working in a real Kestra
  execution** (not just unit tests): registered via API, triggered, watched
  through to `SUCCESS`, logs show correct discovery + idempotent skip
  behavior. Two real bugs found and fixed along the way (see "Infra notes").
- `tests/unit/test_nhs_ingest.py` — 11 unit tests, all passing.
- Quality-report JSON per run in `data/quality_reports/`.

## Milestone 3 — Analytics vertical slice ✅ DONE

- `src/llm_project/analytics/metrics.py` — `compute_provider_test_month_metrics()`
  and `compute_bottleneck_scores()` (3 weighting scenarios: balanced,
  waiting_focused, capacity_focused), per plan.md Step 5's exact formula.
  Handles missing baselines as `None`, never a fabricated `0` (e.g. no
  month-over-month change for a provider/test's first loaded month; no CDC
  component since there's no CDC-to-provider mapping yet). **Verified**:
  East Kent Hospitals MRI May 2026 → 40.82% waiting 6+ weeks, hand-checked
  against the raw fact (5084/12455).
- `src/llm_project/analytics/tools.py` — `get_provider_profile` and
  `rank_provider_waits`, Pydantic-typed I/O, allowlisted test
  codes/metrics, parameterized SQL only, every response carries source
  period + data-quality warnings + execution time. **Verified** against
  real data: `rank_provider_waits(test_code="MRI")` correctly surfaces real
  NHS trusts (Guy's & St Thomas', Royal Papworth, Spire hospitals) with
  real percentages; invalid provider/test codes correctly raise `ToolError`.
- `src/llm_project/app/streamlit_app.py` — **rewritten from scratch**,
  arXiv chat UI fully replaced. Two tabs: "Rank providers" and "Provider
  profile", calling the tools above directly — no LLM/RAG yet (deliberately,
  per plan.md's core principle: numbers come from code, not the model).
  Logs interactions to the existing `conversations` table (reusing
  `db/client.log_conversation`) so the Monitoring page has real data too.
  Verified: page loads (HTTP 200), backend logic verified via direct calls
  above; a live click-through wasn't done this session (browser tooling was
  disconnected — see "Infra notes").

### Exact next steps

**Milestone 4 (RAG)** — not started:
1. Provider-test profile generator (template-based, SQL-sourced numbers,
   plan.md Step 6A) + diagnostic-test profiles + metric definitions +
   methodology docs (6B/6C/6D).
2. Feed these into the *already-reused* `search/` layer (`load_docs()` needs
   to read `data/raw/documents.jsonl` — just populate it; the retrieval code
   itself needs zero changes).
3. Retrieval ground truth (120–150 questions, plan.md Step 8) + evaluation
   (reuse `eval/evaluate_retrieval.py`'s pattern).
4. Exit condition: retrieval evaluation reproducible, best method selected
   (same rigor as the old arXiv project's retrieval eval, which is a good
   reference for the *shape* of this work even though its content is gone).

Then **Milestone 5 (Agent)**: query rewriting/intent (Pydantic-typed, extends
`rag/query_rewrite.py`'s pattern), remaining 7 analytical tools (plan.md Step
11 lists 9 total; 2 done), agent wiring (new `rag/agent.py`, following the
same toyaikit tool-calling shape the deleted arXiv one used, now pointed at
NHS tools + RAG), agent evaluation (100+ cases).

## Things a fresh agent should NOT re-litigate

- The tech-substitution decisions (Kestra not Prefect, minsearch/ES not
  pgvector, Streamlit not Grafana, no FastAPI) — already discussed with the
  user across two clarification rounds and approved in plan mode.
- The MVP scope (4 diagnostic groups, provider-level not
  provider×commissioner, recent months not full 24-36-month backfill).
- Whether to remove the arXiv code — already done, per explicit request.
- Whether `agent/` should be gitignored — already done, per explicit request.
