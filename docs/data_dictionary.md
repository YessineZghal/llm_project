# Data dictionary

Derived from directly inspecting the real source files (see `DATA_SOURCES.md`
for exact URLs/dates), not from documentation alone.

## Source: DM01 monthly extract (`DM01-<MONTH>-<YEAR>-full-extract.csv`)

One row = one (reporting month, provider, commissioner, diagnostic test)
combination. 146,992 rows in the May 2026 file; 456 distinct provider codes;
16 diagnostic-test values (15 named tests + a `TOTAL` roll-up row, which is
excluded during load since it would double-count).

| Column | Type | Notes |
|---|---|---|
| `Period` | string | e.g. `DM01-MAY-2026`. Parsed to an ISO reporting month (`2026-05`). |
| `Provider Parent Org Code` / `Provider Parent Name` | string | Parent organisation; not used in the MVP schema. |
| `Provider Org Code` | string | **Provider identifier** — the field the canonical schema keys on. |
| `Provider Org Name` | string | Display name. |
| `Commissioner Parent Org Code/Name`, `Commissioner Org Code`, `Commissioner Org Name` | string | Commissioner (ICB) breakdown. The MVP aggregates these away to reach provider-level facts (plan.md requires provider-level data); commissioner detail is dropped, not stored per-row. |
| `Diagnostic Tests Sort Order` | int | NHS's own display order; not used. |
| `Diagnostic Tests` | string | Test code. MVP keeps only `MRI`, `CT`, `NON_OBSTETRIC_ULTRASOUND`, `COLONOSCOPY`. |
| `00 < 01 Week` … `12 < 13 Weeks` | int | 13 weekly waiting-list bands. All values verified non-negative, no suppression markers (`*` or blank) found in the May 2026 file — every cell is a plain integer. |
| `13+ Weeks` | int | Longest-wait band. |
| `Total WL` | int | Verified equal to the sum of the 14 band columns above (checked on 500 MRI rows, zero mismatches) — used as a validation check during load, not blindly trusted. |
| `Waiting List Activity` | int | Activity against the waiting list. |
| `Planned Activity` | int | Planned/surveillance activity. |
| `Unscheduled Activity` | int | Unscheduled activity. |
| `Total Activity` | int | Sum of the three activity columns above. |

**Candidate primary key (raw):** (`Period`, `Provider Org Code`,
`Commissioner Org Code`, `Diagnostic Tests`).
**Primary key after MVP aggregation to provider level:** (`Period`,
`Provider Org Code`, `Diagnostic Tests`).

**Null/suppression convention:** none observed — small counts are `0`, not
blank or masked. (If a future month does introduce a suppression marker,
ingestion must fail closed rather than silently coerce it to `0` — see
plan.md Step 3 failure controls.)

**Row-count reconciliation:** `146,992` rows ÷ `16` test values ÷ `456`
providers ≈ `1` commissioner per (provider, test) on average, but this is not
exact — 9,187 rows exist per test value, i.e. 9,187 distinct
(provider, commissioner) pairs, not 456. Aggregation to provider level must
group and sum, not assume one row per provider.

## Source: CDC provider activity (`CDC-Activity-by-Provider-<YEAR>_-<MONTH>.csv`)

One row = one (CDC, diagnostic test, reporting month) combination. 2,862 rows
in the file downloaded 2026-08-02, already covering two reporting months
(`Apr-26`, `May-26`) in a single file.

| Column | Type | Notes |
|---|---|---|
| `Region Code` / `Regional Name` | string | NHS region. |
| `ICB` | string | Integrated Care Board name. |
| `CDC Code` | string | **Community Diagnostic Centre identifier** — not the same identifier space as DM01's `Provider Org Code`. |
| `CDC Name` | string | Display name, e.g. "Barking Community Hospital CDC". |
| `ID` | int | Per-CDC sequence number for the test row; **not** a unique key on its own (resets per CDC). |
| `Diagnostic Test Type` | string | Full test name, e.g. "Magnetic Resonance Imaging", "Computed Tomography" — **different vocabulary than DM01's short codes**; requires an alias mapping (`MRI` ↔ "Magnetic Resonance Imaging", etc.) built during Step 2/3. |
| `Reporting Month` | string | Abbreviated `Mon-YY` (e.g. `May-26`) — parsed to the same ISO reporting-month format as DM01. |
| `Sum of Metric Value` | int | Activity count. |

**Candidate primary key:** (`CDC Code`, `Diagnostic Test Type`,
`Reporting Month`).

**Known limitation (documented, not silently resolved):** CDC activity cannot
be joined to a DM01 provider without an explicit CDC→provider mapping, which
is not present in this file. For the MVP, CDC activity is stored and
retrievable by CDC/ICB/region, and joined to a provider only where such a
mapping is later established; until then, "CDC activity" in a provider
profile is reported as *unavailable* rather than assumed absent (plan.md:
"never treat missing data as zero").

## Answers to Step 1's acceptance-gate questions

- **What does one DM01 row represent?** Waiting-list and activity counts for
  one diagnostic test, at one provider, under one commissioner, in one
  reporting month.
- **Which field identifies the provider?** `Provider Org Code`.
- **Which field identifies the diagnostic test?** `Diagnostic Tests` (DM01) /
  `Diagnostic Test Type` (CDC, different vocabulary — needs the alias map).
- **How are waiting bands represented?** 13 discrete weekly-band columns plus
  a `13+ Weeks` overflow band, all verified to sum to `Total WL`.
- **How is activity represented?** Three activity columns (waiting-list,
  planned, unscheduled) summing to `Total Activity`.
- **How are revisions indicated?** Not encoded in the file itself — handled
  by the source registry treating each (URL, hash) as a distinct version
  (see `DATA_SOURCES.md` §1).
- **Can a row be uniquely identified?** Yes, by the composite keys given
  above.
