# Approved implementation plan (snapshot)

This is a saved copy of the plan approved via Claude Code's plan mode on
2026-08-02, for continuity if a future session/agent doesn't have this
conversation's context. **`agent/PROGRESS.md` is the live status** — read
that first; this file is the unchanging reference for *why* decisions were
made (tech substitutions, scope reductions, milestone sequencing).

---

# ScanFlow AI — rebuild on the existing Kestra/minsearch/ES/Streamlit stack

## Context

`plan.md` (in the repo root) is the user's own detailed 21-step execution plan for
**ScanFlow AI**: a RAG + analytical-agent app answering questions about NHS England
diagnostic waiting-time and capacity data (MRI/CT/ultrasound/colonoscopy wait times,
provider comparisons, bottleneck scores). It's the real subject for this LLM Zoomcamp
project submission.

What actually got built in an earlier session (and what this session initially
continued) is a *different* project — an arXiv-paper RAG/agent assistant — using
Kestra, minsearch, Elasticsearch, Streamlit, and Postgres. That work is functional,
evaluated, and containerized, but answers a different question entirely.

The user's decision (after two rounds of clarification): **build ScanFlow AI's real
subject matter (NHS data), but implement it on the tech already set up** — Kestra
instead of Prefect, minsearch/Elasticsearch instead of Postgres+pgvector, and (as a
proposed, flagged deviation below) Streamlit instead of Grafana, no separate FastAPI
service. The existing arXiv codebase's *infrastructure* (search layer, db/monitoring
pattern, Streamlit scaffolding, Docker Compose services) is reused; its *content*
(arXiv ingestion, prompts, agent tools) is replaced.

Before writing this plan, live verification confirmed plan.md's core data dependency
is real and fetchable right now (not just as described in the plan):

- Downloaded `DM01-MAY-2026-full-extract.zip` from
  `https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/07/DM01-MAY-2026-full-extract_8BN1G.zip`
  → 147K rows, one row per (period, provider, commissioner, diagnostic test), with
  exactly the columns plan.md's canonical model expects: 13 weekly waiting bands
  (`00 < 01 Week` … `13+ Weeks`), `Total WL`, `Waiting List Activity`,
  `Planned Activity`, `Unscheduled Activity`, `Total Activity`.
- Confirmed all 4 MVP diagnostic groups are present as clean values:
  `MRI`, `CT`, `NON_OBSTETRIC_ULTRASOUND`, `COLONOSCOPY` (plus 12 others + a `TOTAL`
  row ignored), across 456+ distinct provider codes.
- Downloaded the CDC provider-activity file (small, single CSV,
  `CDC-Activity-by-Provider-2026-27_-May.csv`) — also real and directly fetchable.
- A national (not provider-level) time-series XLS also exists with sheets like
  `Total Waiting List`, `6+ Week Waits %`, `13+ Week Waits` — useful later as
  definitional/context source material, not a substitute for the provider-level
  monthly extracts.
- New monthly files live under year-specific pages (e.g.
  `.../monthly-diagnostics-data-2026-27/`), each linking that month's ZIP — so
  pulling N months means iterating year-pages and their monthly links, not one
  fixed URL. Confirmed working via `src/llm_project/ingest/nhs_discover.py`.

## Tech substitutions vs. plan.md (what's being reused, not rebuilt)

| plan.md | Actual implementation |
|---|---|
| Prefect | **Kestra** — same pattern as the existing `flows/ingest_arxiv.yaml` (Docker task runner against the app image), new `flows/ingest_diagnostics.yaml` |
| FastAPI backend | **Dropped.** Streamlit calls plain Python service modules directly, same as the current app. Course rubric ("Interface") only requires *one* of UI/webapp/API — Streamlit alone satisfies it. |
| PostgreSQL + pgvector retrieval | **minsearch (text + vector) + Elasticsearch (text/kNN/hybrid via RRF) + cross-encoder rerank** — the existing `src/llm_project/search/*` modules, reused verbatim. They're already generic over `list[dict]` documents; they just get pointed at the new NHS RAG corpus instead of arXiv abstracts. This gives 6 retrieval approaches, already exceeding plan.md's "≥3 approaches" requirement. |
| Grafana monitoring | **Streamlit monitoring dashboard** — same pattern as the one already built and browser-verified (`app/pages/1_Monitoring.py` + `db/client.py` query helpers), extended with plan.md's richer interaction-log schema (intent, tools_called, retrieval scores, tokens, cost). |
| Postgres for structured facts/derived metrics | **Kept as-is** — this is genuinely required regardless of orchestration choice; already have SQLAlchemy + psycopg wired up. |
| Docker Compose: frontend/backend/postgres/prefect-server/prefect-worker/grafana | **Reuse the existing `docker-compose.yml` skeleton** (elasticsearch, app_postgres, kestra, kestra_postgres, app) — no separate prefect or grafana services. |

Scope reductions proposed to keep this achievable (all consistent with plan.md's
own "small vertical slice first" principle and its own phase-two/stretch/out-of-scope
lists):
- Skip pgvector, Grafana, FastAPI, CI (can revisit after the vertical slice works).
- Start with the 4 MVP diagnostic groups and a handful of recent complete months
  (not 24-36) to keep local iteration fast; widen the month range once the pipeline
  is proven idempotent and correct.
- No RTT, workforce data, maps, cloud deployment, multilingual — already deferred
  in plan.md itself.

The existing arXiv project files are **not deleted** — `ingest/arxiv_source.py`,
`ingest/pipeline.py`, `data/raw/papers.jsonl`, `data/eval/*` stay in place but become
unused once the app is repointed at NHS data.

## What's reused verbatim

- `src/llm_project/search/` (`minsearch_index.py`, `es_index.py`, `embeddings.py`,
  `rerank.py`, `retriever.py`) — no changes needed, just a new `load_docs()` source.
- `src/llm_project/db/` pattern (SQLAlchemy `Base`, engine/session helpers,
  `log_conversation`/`log_feedback`-style logging) — schema extended, pattern kept.
- `src/llm_project/app/` Streamlit scaffolding + `pages/` multipage convention.
- `docker-compose.yml` services (elasticsearch, app_postgres, kestra,
  kestra_postgres, app) and `Dockerfile`.
- The Kestra flow pattern from `flows/ingest_arxiv.yaml`.

## What's new

- Real NHS data ingestion: download → hash → validate → normalize → load, filtered
  to the 4 MVP tests and aggregated to provider level.
- Canonical Postgres schema: dimensions (`providers`, `diagnostic_tests`,
  `reporting_periods`, `source_files`) + facts (`diagnostic_waiting_facts`,
  `diagnostic_activity_facts`, `cdc_activity_facts`) + derived
  (`provider_test_month_metrics`, `bottleneck_scores`).
- Derived-metrics library + bottleneck score (3 weighting scenarios), per plan.md
  Step 5's exact formula.
- RAG corpus generator: provider-test profiles, diagnostic-test profiles, metric
  definitions, methodology docs — numbers come from SQL/templates, never the LLM
  (plan.md Step 6) — fed into the reused `search/` layer.
- Query rewriting + intent classification (Pydantic-typed, OpenAI-backed) — same
  style as the existing `rag/query_rewrite.py`, extended with entity/date extraction.
- 9 controlled analytical tools (parameterized SQL, typed I/O, allowlisted
  metrics/fields) per plan.md Step 11.
- Agent: extend the existing toyaikit tool-calling pattern (`rag/agent.py`) with the
  analytical tools + RAG retrieval + routing between them.
- Grounded answer generation: evidence package, citations, reporting periods,
  non-causal language, limitations (plan.md Step 13's response structure).
- 6-page Streamlit UI (Ask ScanFlow / Diagnostic Explorer / Provider Comparison /
  Bottleneck Ranking / Capacity Scenario / Methodology).
- Evaluations: retrieval (reuse `eval/evaluate_retrieval.py`'s pattern against new
  ground truth), agent (new — 100+ cases, tool/argument accuracy), LLM answer (new
  — 3 pipeline configs A/B/C per plan.md Step 14).
- README rewrite to plan.md's structure + `DATA_SOURCES.md`.

## Execution sequencing (8 milestones — see agent/PROGRESS.md for current status)

1. **Foundation** — `DATA_SOURCES.md` + `docs/data_dictionary.md`, canonical
   Postgres schema + migration, load real months of DM01 + the CDC file.
   *Exit: schema loads real data, constraints reject bad rows.*
2. **Reliable ingestion** — deterministic download→hash→validate→normalize→load
   script (idempotent), then wrapped in `flows/ingest_diagnostics.yaml` (Kestra).
   *Exit: running ingestion twice does not duplicate records.*
3. **Analytics vertical slice** — derived metrics + bottleneck score, one analytical
   tool, minimal Streamlit answer. *Exit: one real question → SQL-backed, cited
   answer with source period.*
4. **RAG** — profile/definition generation, indexed via the reused `search/` layer,
   retrieval ground truth (120–150 questions) + evaluation. *Exit: retrieval
   evaluation reproducible, best method selected.*
5. **Agent** — query rewriting/intent, remaining 8 tools, agent wiring, agent
   evaluation (100+ cases). *Exit: supported questions route correctly, numbers
   match direct SQL.*
6. **Quality & UX** — grounded generation + citations, LLM evaluation (3 configs),
   full 6-page Streamlit UI, feedback. *Exit: production config chosen from measured
   results; browser-verified end to end.*
7. **Operations** — extend the monitoring dashboard to the richer log schema/charts,
   finalize Docker Compose.
8. **Submission** — README rewrite, `DATA_SOURCES.md` finalized, rubric audit
   against plan.md's own final checklist.

## Verification per milestone

- M1: show real row counts loaded, demonstrate a constraint rejecting an invalid row.
- M2: run ingestion twice, prove zero duplicate records.
- M3: ask one real question through Streamlit, confirm the number matches a direct
  SQL query.
- M4: run retrieval evaluation, show hit-rate/MRR comparison table.
- M5: run agent evaluation, show tool-selection/argument accuracy.
- M6: run LLM evaluation across the 3 configs; browser-test the live UI.
- M7: browser-test the monitoring dashboard with real logged data.
- Final: `docker compose up --build` from a clean state as a smoke test.
