# ScanFlow AI — live progress

**Read this file first in any new session.** It's the up-to-date status; the
unchanging rationale/plan is in `agent/PLAN.md`. If you're a fresh agent with
no memory of this conversation: read this file, then `agent/PLAN.md`, then
`plan.md` (original 21-step spec) and `DATA_SOURCES.md` /
`docs/data_dictionary.md` before touching code.

Last updated: 2026-08-03 (mid-session).

## TL;DR current state

- **Milestone 1 (Foundation): done and verified.**
- **Milestone 2 (Reliable ingestion): code done and verified; blocked on
  infrastructure (see "Current blocker" below), not on remaining work.**
- Everything from here is real, tested against real NHS data — nothing is
  aspirational/untested in what's marked done below.

## Current blocker (read this before doing anything with Docker)

The host disk filled to 100% (117MB free of 460GB) partway through this
session, during a `docker compose build app` run. This caused:
1. The build itself to fail (`input/output error` on a `chmod`).
2. `docker builder prune` to fail with `ENOSPC`.
3. Even Claude Code's own task-tracking writes to fail with `ENOSPC` briefly.

Disk space was freed by the user (back to 64GB free). But afterwards:
- The `app_postgres` container started throwing
  `FATAL: could not open file "global/pg_filenode.map": Input/output error"`
  — its Postgres data files likely got corrupted when disk-full writes failed
  mid-flight. **The NHS data loaded during Milestone 1 (3 months, 464
  providers, 5,480 facts) may need to be re-loaded once Postgres is healthy
  again** — this is cheap and fast to redo (see "How to re-verify" below),
  ingestion is idempotent and deterministic, nothing is lost conceptually.
- `docker ps` itself started hanging/timing out again shortly after, which
  suggests possible damage to Docker Desktop's own VM disk image
  (`~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw` on
  macOS — Docker Desktop stores all images/volumes/containers inside this
  one file), not just the Postgres container.

**This needs a human decision, not another automated retry loop:**
- Option A: Restart Docker Desktop again and see if it's transient (low
  risk, already tried once successfully earlier in the session).
- Option B: Recreate just the `app_postgres` volume
  (`docker compose down -v app_postgres` equivalent, or
  `docker volume rm llm_project_app_postgres_data`) if Docker responds — loses
  only the re-loadable NHS data, not other projects' containers.
- Option C: Docker Desktop's "Clean / Purge data" / full VM reset — fixes
  everything but **also wipes the user's unrelated `auctionnow-*` project
  containers** seen running in this same Docker Desktop instance. Do **not**
  do this without the user's explicit go-ahead, since it affects their other
  work.

Do not keep blindly re-running `docker ps`/`docker compose` commands hoping
one works — if Docker is still unresponsive, stop and ask the user which
option they want.

## Milestone 1 — Foundation ✅ DONE

Real NHS data verified end-to-end (before the disk/Postgres issue above):
- `DATA_SOURCES.md` — verified real URLs for DM01 (monthly diagnostics) and
  CDC files, licence/attribution.
- `docs/data_dictionary.md` — real column-by-column schema read off the
  actual downloaded files (not guessed).
- `database/schema.sql` + `src/llm_project/db/nhs_schema.py` — canonical
  schema: 4 dimension tables (`providers`, `diagnostic_tests`,
  `reporting_periods`, `source_files`), 3 fact tables
  (`diagnostic_waiting_facts`, `diagnostic_activity_facts`,
  `cdc_activity_facts`), 2 derived tables (`provider_test_month_metrics`,
  `bottleneck_scores`). Shares `Base`/engine with the pre-existing
  `db/models.py` (monitoring tables `conversations`/`feedback`, from the
  earlier arXiv-project work — untouched, unrelated).
- Loaded 3 real months (March/April/May 2026 DM01 + the CDC file) → 464
  providers, 4 diagnostic tests (MRI/CT/NON_OBSTETRIC_ULTRASOUND/COLONOSCOPY),
  5,480 waiting facts, 5,480 activity facts, 853 CDC facts.
- All three of plan.md Step 2's acceptance checks verified against the live
  DB: duplicate facts rejected (unique constraint), invalid percentages
  rejected (check constraint), every fact traceable to a source file
  (NOT NULL FK) — see the inline test script output earlier in this
  conversation, or re-run the equivalent checks in
  `tests/unit/test_nhs_ingest.py`.

## Milestone 2 — Reliable ingestion 🟡 CODE DONE, blocked on infra above

- `src/llm_project/ingest/nhs_source.py` — DM01 ZIP + CDC CSV parsers.
  Validates Total WL == sum(weekly bands) and Total Activity == sum(activity
  columns) at parse time; raises (fails closed) on mismatch.
- `src/llm_project/ingest/nhs_pipeline.py` — deterministic loader:
  download → hash → skip-if-already-ingested (by `dataset` + `sha256` in
  `source_files`) → aggregate DM01's provider×commissioner×test rows to
  provider×test → load. **Verified idempotent**: re-running against an
  already-ingested URL returns `status: skipped_already_ingested`, no
  duplicate rows. Also writes a JSON quality report per run to
  `data/quality_reports/<timestamp>.json` (plan.md Step 3 deliverable).
- `src/llm_project/ingest/nhs_discover.py` — scrapes the live NHS
  publication pages (BeautifulSoup) for the current DM01/CDC URLs instead of
  hardcoding one file. **Verified against the real site** — see
  `agent/PLAN.md`'s verification notes.
- `src/llm_project/ingest/nhs_discovered_run.py` — the discover-then-load
  entrypoint; this is what the Kestra flow runs.
- `flows/ingest_diagnostics.yaml` — Kestra flow, same Docker-task-runner
  pattern as `flows/ingest_arxiv.yaml`, daily schedule. **Not yet tested for
  real inside Kestra** — this needs the `llm-project-app:latest` Docker image
  built, which is exactly what's blocked (see "Current blocker").
- `tests/unit/test_nhs_ingest.py` — 11 unit tests, all passing, covering
  parsing, validation-rejection, aggregation, period-label parsing
  (DM01's `DM01-MAY-2026` and CDC's `May-26` formats), and fiscal-year-slug
  boundary logic. Run with `uv run pytest tests/unit/ -v`.

### Exact next steps once Docker/Postgres is healthy again

1. `docker compose up -d app_postgres` (recreate if the volume was removed).
2. Re-run Milestone 1's load (idempotent, so safe even if some data survived):
   ```
   uv run python -m llm_project.ingest.nhs_pipeline \
     "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/05/DM01-MARCH-2026-full-extract_32W3L.zip" \
     "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/06/DM01-APRIL-2026-full-extract.zip" \
     "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/07/DM01-MAY-2026-full-extract_8BN1G.zip" \
     --cdc "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/07/CDC-Activity-by-Provider-2026-27_-May.csv"
   ```
   (Or just `uv run python -m llm_project.ingest.nhs_discovered_run` for the
   2 current-fiscal-year months + latest CDC file — discovery only finds
   April+May since the 2026-27 fiscal year just started; March came from the
   prior year's page, passed explicitly above.)
3. `docker compose build app` (was mid-build when disk filled — confirm it
   completes clean now).
4. Bring up Kestra (`docker compose up -d kestra kestra_postgres`) and
   actually trigger `ingest_diagnostics` there for real — this flow has only
   been written and unit-tested, not run inside Kestra yet.
5. Mark task #12 (flows/ingest_diagnostics.yaml) and #13 (quality
   report + tests — tests done, report-writing done, just needs the
   end-to-end confirmation) complete, then move to **Milestone 3**
   (derived metrics + bottleneck score + one analytical tool + minimal
   Streamlit answer — see `agent/PLAN.md`).

## Milestones 3–8

Not started yet. Full detail in `agent/PLAN.md`'s "Execution sequencing"
section — each has an explicit exit condition to verify against real
data/queries before moving on, same rigor as Milestones 1–2 above.

## Things a fresh agent should NOT re-litigate

- The tech-substitution decisions (Kestra not Prefect, minsearch/ES not
  pgvector, Streamlit not Grafana, no FastAPI) — already discussed with the
  user across two clarification rounds and approved in plan mode. Don't
  re-ask; just follow `agent/PLAN.md`.
- Whether to keep or delete the old arXiv-project code — explicitly left
  in place, unused, not blocking anything. Leave it alone unless asked.
- The MVP scope (4 diagnostic groups, provider-level not
  provider×commissioner, recent months not full 24-36-month backfill) —
  already a deliberate, approved scope reduction, not an oversight.
