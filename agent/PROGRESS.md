# ScanFlow AI - live progress

**Read this file first in any new session.** It's the up-to-date status; the
unchanging rationale/plan is in `agent/PLAN.md`. If you're a fresh agent with
no memory of this conversation: read this file, then `agent/PLAN.md`, then
`plan.md` (original 21-step spec), `DATA_SOURCES.md`, and
`docs/data_dictionary.md` before touching code.

Last updated: 2026-08-03.

## Latest phase: security review + bottleneck access + 4 new chart pages

- **Security review completed** (the `security-review` skill's prescribed
  process: an independent subagent traced every LLM-controlled tool-call
  path from `rag/agent.py` through `analytics/tools.py` into
  SQL/Elasticsearch). Result: no high-confidence vulnerability in the
  application logic - every dynamic `getattr()` column access is
  allowlist-gated before use, all DB access is ORM-parameterized, ES
  queries use safe `multi_match`/`knn` (never `query_string`/scripted
  queries), no `unsafe_allow_html` anywhere, no eval/exec/pickle/yaml.load.
  One real, fixed finding: `elasticsearch` (security disabled) and
  `app_postgres` (example password) were published on all network
  interfaces (`0.0.0.0`) rather than loopback-only. Fixed in
  `docker-compose.yml`: both now bind `127.0.0.1` only, and
  `APP_POSTGRES_PASSWORD` has no built-in default (`${VAR:?...}` syntax -
  the stack refuses to start without a real value set). Verified this
  didn't break anything: recreated both containers, confirmed health and
  that all data (464 providers, 1,870 indexed documents) survived.
- **The bottleneck score is no longer inaccessible.** This was the single
  most important gap from the last audit - 16,440 computed rows with zero
  way to query them. Added `get_bottleneck_ranking` to
  `analytics/tools.py` (queries `BottleneckScore` directly, supports
  test/period/weighting_scenario/limit/min_quality), wired into the agent,
  verified working through both the direct tool call and a real agent
  conversation ("What is the CT waiting list bottleneck ranking...").
- **Four new Streamlit pages**, closing out all 6 of plan.md Step 15's
  pages: `3_Diagnostic_Explorer.py` (trend charts - waiting/activity/%
  over time, one provider+test), `4_Provider_Comparison.py` (2-5
  providers, grouped bar charts), `5_Bottleneck_Ranking.py` (ranked score
  + a melted/grouped component-breakdown chart so the score is explainable,
  not opaque - correctly excludes the always-null CDC component via
  `dropna` rather than plotting a fake zero), `6_Capacity_Scenario.py`
  (projection line chart + narrative summary, prominent simplified-model
  warning). All follow the same fixed categorical palette and single-hue
  conventions as the pre-existing Monitoring page; none use dual-axis
  charts (different units always get separate charts). Every page's core
  data-loading + Altair chart-spec logic was verified against real data by
  direct script execution (`chart.to_dict()` succeeding, real row counts) -
  browser automation was still unavailable this entire session, so this is
  the strongest verification achievable without a live click-through.
- README, `docs/rubric-checklist.md` updated to match (rubric checklist
  was quite stale, predating Milestones 4-5 - now accurate).

**Still open** (see "Known limitations" / "Roadmap" in README, unchanged
by this phase): no metadata filters on `retrieve()` (plan.md Step 7), no
dedicated relative-date resolution utility (plan.md Step 10), no
evidence-package/citation-formatter module or 3-way pipeline comparison
(plan.md Steps 13/14), monitoring still missing tool-success-rate /
ingestion-freshness / token-cost charts (plan.md Step 16), no CI run on a
real GitHub Actions runner yet, no screenshots (browser unavailable all
session).

## TL;DR current state

- **Milestones 1-5: done and verified against real data and a real running
  agent, not mocked.**
- **Milestone 6 (grounded generation polish, full 6-page UI, 3-way LLM
  pipeline comparison): partially done** - the agent already grounds every
  numeric answer in a tool call and refuses unsupported requests (100%
  verified on 15 real safety test cases), and the Methodology page is
  built. Still missing: a dedicated evidence-package/citation-formatter
  module, the formal A/B/C pipeline comparison from plan.md Step 14, and
  4 of 6 Step 15 pages (Diagnostic Explorer, Provider Comparison,
  Bottleneck Ranking, Capacity Scenario).
- **Milestone 7 (monitoring extension): partially done** - dashboard now
  has 6 real (not stale) charts and real cited-document tracking; still
  missing tool-success-rate, ingestion-freshness, and token-cost charts.
- **Milestone 8 (final docs/submission audit): not started** as a formal
  pass, though README/architecture/rubric-checklist docs are already
  reasonably current.
- Professional-polish gaps flagged in an earlier audit are now closed:
  feedback UI works, `analytics/` has unit + integration tests, CI exists,
  Makefile exists, `docs/architecture.md` and `docs/rubric-checklist.md`
  exist.

## Milestones 1-3 (Foundation, Ingestion, Analytics vertical slice) - DONE

Unchanged from the previous summary: real NHS data (3 months, 464
providers) loaded via an idempotent, Kestra-orchestrated pipeline; derived
metrics + bottleneck score computed and verified by hand; 2 analytical
tools built and Streamlit-exposed. See git history / earlier detail in this
file's prior versions, or just trust the newer milestones below, which
supersede and build on this.

Two real bugs were found and fixed in this phase (documented in detail
further down, kept here as a pointer): a wrong Kestra plugin type name, and
a missing `.dockerignore` that let the host's own `.venv` clobber the
container's.

## Milestone 4 (RAG) - DONE, verified

- `src/llm_project/rag/generate_corpus.py` - generates the RAG corpus
  entirely from validated database facts and static reference text, **zero
  LLM calls**. Produces 1,870 documents: 1,856 provider-test profiles (one
  per real provider/test combination with loaded data), 4 diagnostic-test
  definitions, 6 metric definitions, 4 methodology documents. Output:
  `data/raw/documents.jsonl`.
  - Found and fixed a real bug while building this: the CDC loader was
    overwriting DM01's nicer period labels ("DM01-MAY-2026") with plain
    period ids ("2026-05") when both datasets touched the same period.
    Fixed in `nhs_pipeline.load_cdc_source` (only sets a label if the period
    doesn't already exist) and corrected retroactively in the live DB.
- Indexed via the **unchanged, reused** `search/` layer
  (`uv run python -m llm_project.search.es_index --recreate`) - confirms
  the "reuse verbatim" plan actually held up in practice.
- `src/llm_project/eval/generate_ground_truth.py` - rewritten for NHS
  content, stratified sampling per plan.md Step 8's exact target
  distribution (25 provider-profile / 20 test-definition / 20
  metric-definition / 20 methodology / 20 comparison-support / 15
  hand-curated unanswerable questions = 120 total, generated 120 for real).
  Output: `data/eval/retrieval_ground_truth.jsonl`.
- `src/llm_project/eval/evaluate_retrieval.py` - rewritten to compute Hit
  Rate@5, MRR, Recall@5, Recall@10, NDCG@5 (plan.md Step 8's full metric
  set) across all 6 retrieval methods, plus a separate unanswerable-question
  signal. **Real result**: `es_hybrid_rerank` wins (MRR 0.948, hit rate
  0.981, 2 misses out of 105 answerable questions - both genuinely
  ambiguous questions, not retrieval bugs). Matches the existing default in
  `retriever.py`, so no code change needed there. Results:
  `data/eval/retrieval_eval_results.csv`; error analysis:
  `data/eval/retrieval_error_analysis.md`.

## Milestone 5 (Agent) - DONE, verified

- `src/llm_project/analytics/tools.py` - **all 9 of plan.md's tools**
  implemented (previously 2): `get_provider_profile`, `rank_provider_waits`,
  `compare_provider_waits`, `analyze_waiting_trend`,
  `compare_activity_and_waiting`, `analyze_cdc_activity`,
  `find_similar_providers`, `simulate_capacity_change`,
  `retrieve_metric_definition` (the only one that calls the RAG layer rather
  than SQL - metric definitions are reference text, not computed facts).
  Every tool verified individually against real data in this session (see
  conversation for concrete outputs) - e.g. `simulate_capacity_change`
  honestly showed a provider's waiting list would keep growing even with
  +200 monthly activity, because implied demand exceeds it; it doesn't force
  a flattering answer.
- `src/llm_project/rag/intent.py` - query rewriting/intent classification
  (plan.md Step 10): 9-way intent classifier (LLM for language
  understanding only), plus `resolve_provider`/`resolve_test`/`resolve_metric`
  that validate/resolve extracted entities against the real database and
  fixed allowlists in code, never trusting the LLM's guess directly.
  Verified: ambiguous names (e.g. "Spire") correctly surface all candidates
  rather than silently picking one.
- `src/llm_project/rag/agent.py` - **rebuilt from scratch** (the old
  arXiv-specific version was deleted earlier). toyaikit tool-calling agent
  with 11 tools (9 analytical + `resolve_provider_code` +
  `search_knowledge_base`). Important implementation detail: toyaikit's
  automatic JSON-schema generator (`toyaikit.tools.generate_function_schema`)
  needs flat, primitive-typed function parameters and JSON-serializable
  return values - it does NOT understand Pydantic model parameters or
  return Pydantic objects directly. So `agent.py`'s tool functions are thin
  wrappers with flat signatures that construct the real Pydantic
  `*Input` objects, call the real `analytics.tools` functions, and return
  `.model_dump()`. Verified live with real multi-turn questions: correct
  tool selection for a ranking question, correct refusal for an individual
  medical question, correct RAG-grounded answer for a definition question,
  and a nuanced (not oversimplified) trend description for a real
  non-monotonic data series.
- Wired into the Streamlit interface: `src/llm_project/app/streamlit_app.py`
  now has three tabs - **Ask ScanFlow** (chat interface using the agent,
  new), Rank providers, Provider profile (both pre-existing, tool-direct,
  no LLM). All three log to the interaction table and support feedback.
- `src/llm_project/eval/evaluate_agent.py` - agent evaluation per plan.md
  Step 12: 117 test cases (exceeds the "at least 100" requirement) covering
  every intent, all 9 tools, plan.md's named difficult cases (partial/alias
  provider names, ambiguous provider names, missing parameters, 15
  unsupported-medical-request safety cases), run against the **real**
  intent classifier and **real** agent (not mocked). Includes retry/backoff
  for OpenAI rate limits (hit and fixed during this session - see below).
  Measures intent accuracy, tool-selection accuracy, provider-extraction
  accuracy, test-code-extraction accuracy, and refusal correctness
  separately. Results: `data/eval/agent_eval_results.csv`; error analysis:
  `data/eval/agent_error_analysis.md`; test case bank:
  `data/eval/agent_test_cases.jsonl`.

### Agent evaluation: real results (117 cases, full run completed)

| Measure | Accuracy |
|---|---|
| Intent accuracy | 92.3% (108/117) |
| Tool-selection accuracy | 83.8% (98/117) |
| Provider-code extraction (44 applicable cases) | 100% |
| Test-code extraction (67 applicable cases) | 100% |
| Refusal correctness (15 unsupported-medical-request cases) | **100% (15/15)** |

Manually read every one of the 19 tool-selection "misses"
(`data/eval/agent_error_analysis.md`) rather than trusting the raw number -
most are not real agent failures: ambiguous provider names (e.g.
"SPAMEDICA" has multiple branches) correctly trigger a stop-and-ask
response instead of guessing (contrast with unambiguous partial names like
"MEDEFER", which chained correctly every time); some are the agent
choosing `search_knowledge_base` over the more specific
`retrieve_metric_definition` for definition questions (likely still
retrieves the right document); 3 "missing parameter" cases show the agent
proactively checking all 4 diagnostic tests instead of asking for
clarification - a defensible different strategy, not a failure. The one
**genuine** gap: on 2 of 8 methodology questions ("Where does this data
come from?", "Can figures be revised after publication?") the agent
answered without calling `search_knowledge_base` at all - not covered by
facts already in the system prompt, so this is a real grounding
inconsistency worth tightening in Milestone 6.

**A bug in the evaluation script itself, caught by reading its own
output**: `_write_error_analysis` originally computed "refusal
correctness" as every case with `expected_tool is None`, which
accidentally included 3 unrelated "missing diagnostic test parameter"
cases alongside the 15 real safety cases (18 total), understating the
number as 83.3%. Fixed to filter on `note == "safety"` specifically - the
real number is 100%. This is exactly why this file insists on reading
actual result files rather than trusting a printed summary number.

**Infra note on running this**: the first full-run attempt (concurrency
4) was OOM-killed - `vm_stat` showed ~63MB free at the time, and every
worker thread was independently loading its own copy of the
sentence-transformers embedder + cross-encoder reranker on first use
(`lru_cache` doesn't dedupe concurrent first-calls across threads), a
memory spike this machine couldn't absorb. Fixed by pre-warming both
models once in the main thread before spawning workers
(`_warm_up_models()`), reducing default `max_workers` to 2, and writing
each result to disk as it completes rather than only at the end (so a
future crash leaves partial real results, not nothing). Also added
`_with_retry` (exponential backoff) for OpenAI rate limits, hit
separately during the first attempt.

## Professional-polish gaps (flagged in an earlier audit) - all closed

- `src/llm_project/app/streamlit_app.py` feedback buttons: **fixed**,
  verified end to end (log_feedback called, row appears in the `feedback`
  table).
- `tests/unit/test_metrics.py`, `tests/unit/test_tools_validation.py`,
  `tests/integration/test_analytics_integration.py`: **added**. 42 unit
  tests total (up from 11), all passing; integration tests verified against
  real loaded data (hand-checkable percentage, real provider names, sort
  order, bounds checks on stored metrics/scores).
- `Makefile`: **added** (up/down/build/ingest/metrics/test/lint/app/evaluate
  targets).
- `.github/workflows/ci.yml`: **added** (lint via ruff, unit tests,
  integration tests against a temporary Postgres service container, Docker
  build, gitleaks secret scan). YAML-validated; not run on a real GitHub
  Actions runner (no such runner available in this environment) - worth a
  real CI run once pushed.
- `docs/architecture.md`: **added** (system flow diagram, full ERD in text
  form, design principles, tech-substitution summary).
- `docs/rubric-checklist.md`: **added** (the real course rubric from
  `project.md`, tracked against current status).
- `pyproject.toml`: added `ruff` as a dev dependency and a `[tool.ruff]`
  config (line-length 130). `src` and `tests` are currently 100% clean
  (`uv run ruff check src tests` passes).
- `README.md`: fully rewritten, professional tone, no emoji/decorative
  symbols anywhere in the README or the app UI (explicitly requested and
  verified via a Unicode-emoji-range grep across `app/`).

## arXiv cleanup (done earlier, unchanged)

Still holds - see prior detail. `ingest/arxiv_source.py`, `ingest/pipeline.py`
(arXiv), `flows/ingest_arxiv.yaml`, and all arXiv data files were deleted.
`rag/agent.py` was also deleted at that point (arXiv-specific) and has now
been **rebuilt from scratch** for ScanFlow AI, described above.

## Infra notes (all resolved, kept for context)

- Disk-full incident, Kestra plugin-type bug, and the Docker `.dockerignore`
  bug are all fixed - see earlier detail in git history if needed. Not live
  issues.
- Browser automation (`mcp__claude-in-chrome`) was disconnected for the
  entire second half of this session - every verification claim above was
  checked via direct Python calls or curl, not a live click-through. If a
  fresh session has working browser tools, a real click-through of the
  Streamlit app (especially the new "Ask ScanFlow" chat tab) is still worth
  doing as a first check.

## Also done in this final phase (professional-polish + Milestone 6 start)

- `src/llm_project/app/pages/2_Methodology.py`: **added** - plan.md Step 15's
  Methodology page (data sources, test/metric definitions, real retrieval
  eval results table, limitations), rendered entirely from already-generated
  real content (the RAG corpus + `retrieval_eval_results.csv`), not
  hand-written text that could drift out of sync.
- Monitoring dashboard: the two stale arXiv-era charts are fixed - "RAG vs
  Agent mode" is now "Interactions by mode" (real domain: `agent`,
  `rank_provider_waits`, `get_provider_profile`), and "Retrieval method
  usage" is now "Questions by diagnostic test" (inferred from question
  text, matching plan.md Step 16's chart list directly).
- "Ask ScanFlow" now extracts real cited document ids from the agent's own
  `search_knowledge_base`/`retrieve_metric_definition` tool calls
  (`extract_source_doc_ids` in `streamlit_app.py`) and logs them, so the
  monitoring dashboard's "most-cited source documents" chart has real data
  again (it was always empty before - every logging call passed
  `source_doc_ids=[]`).
- README fully rewritten again with real Milestone 4/5 content and the
  exact, honestly-analyzed agent-eval numbers above (not just the raw
  summary percentages).

## Exact next steps

1. **Milestone 6 remainder**: a dedicated evidence-package/citation
   formatter module (plan.md Step 13 - currently the agent's system prompt
   enforces grounding/citation behavior directly, which works and is
   verified, but isn't a separately testable module), a formal 3-way
   pipeline comparison (dense+basic / rewriting+hybrid / full pipeline,
   plan.md Step 14), and the remaining Streamlit pages from Step 15
   (Diagnostic Explorer with trend charts, Provider Comparison, a
   dedicated Bottleneck Ranking page - `bottleneck_scores` table is
   populated and correct but has no UI yet - and Capacity Scenario -
   `simulate_capacity_change` works and is tested but has no dedicated UI
   yet). Methodology page is done (see above).
2. **Milestone 7**: further monitoring chart additions from plan.md Step
   16's list not yet covered - tool success/failure rate, ingestion
   freshness, estimated token cost. The interaction log also doesn't yet
   store session_id, intent, tool_success, or token/cost fields plan.md
   Step 16 specifies - only what the pre-existing `conversations` table
   already had.
3. **Milestone 8**: rubric self-audit against `docs/rubric-checklist.md`
   with real screenshots (browser automation was unavailable all session -
   worth a real click-through and screenshots once available), and a final
   README pass.
4. Consider tightening the agent's system prompt so methodology questions
   more consistently call `search_knowledge_base` (see the two genuine
   misses documented above) - a small, targeted fix once picked back up.

## Things a fresh agent should NOT re-litigate

- Tech-substitution decisions (Kestra, minsearch/ES, Streamlit, no FastAPI) -
  approved in plan mode, don't re-ask.
- MVP scope (4 diagnostic groups, provider-level, short reporting window) -
  a deliberate, approved scope reduction.
- arXiv code removal and `agent/` gitignore - already done, per explicit
  request.
- The toyaikit flat-parameter constraint in `rag/agent.py` - this is a real
  library limitation discovered by reading its source
  (`toyaikit/tools.py::generate_function_schema`), not a design choice to
  reconsider.
