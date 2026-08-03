# Data sources

ScanFlow AI uses publicly published NHS England statistics. This file is the
source registry required by the project plan: what each dataset is, where it
comes from, and exactly which files were used.

## 1. Monthly Diagnostic Waiting Times and Activity (DM01)

- **Purpose:** primary waiting-list and activity data — one row per
  (reporting month, provider, commissioner, diagnostic test).
- **Official owner:** NHS England.
- **Publication page:**
  https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/monthly-diagnostics-waiting-times-and-activity/
- **Current publication-year page:**
  https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/monthly-diagnostics-waiting-times-and-activity/monthly-diagnostics-data-2026-27/
- **File pattern:** each publication-year page links one ZIP per reporting
  month, e.g.
  `https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/<year>/<month-num>/DM01-<MONTH>-<YEAR>-full-extract*.zip`
  (filenames carry a random suffix, e.g. `_8BN1G`, that changes per file —
  ingestion must discover the link from the page, not construct the URL).
  Each ZIP contains one CSV.
- **File used for initial development:**
  - URL: `https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/07/DM01-MAY-2026-full-extract_8BN1G.zip`
  - Downloaded: 2026-08-02
  - Reporting period: May 2026 (`DM01-MAY-2026`)
  - Extracted CSV: `DM01-MAY-2026-full-extract.csv`, 146,992 data rows, 45MB
  - SHA-256: computed at ingestion time and stored in `source_files` (see
    `docs/data_dictionary.md`); not hand-recorded here since the plan requires
    every ingestion run to hash and store it automatically, not manually.
- **Historical months:** obtained the same way from each year's publication
  page (`monthly-diagnostics-data-<YYYY>-<YY>/`); there is no single
  multi-month file at provider level (a national-aggregate time series file
  exists but does not break down by provider — see below).
- **Revisions:** NHS England may revise a previously published month. The
  source registry treats every (file URL, hash) pair as a distinct source
  version; a re-published file for an already-ingested month is stored as a
  new `source_files` row and supersedes the prior one rather than silently
  overwriting it.

## 2. Community Diagnostic Centre (CDC) activity

- **Purpose:** CDC-level diagnostic activity, supplementary to DM01.
- **Official owner:** NHS England.
- **Publication page:**
  https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/cdc-management-information/
- **File used for initial development:**
  - CSV: `https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/07/CDC-Activity-by-Provider-2026-27_-May.csv`
  - XLSX equivalent: `https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/07/CDC-Activity-by-Provider-2026-27_May.xlsx`
  - Downloaded: 2026-08-02
  - Reporting periods covered: this single file already contains multiple
    months per row (`Reporting Month` column, e.g. `Apr-26`, `May-26`) — 2,862
    data rows.
  - Next scheduled release (per the page): 2026-08-13.
- **Important structural note:** CDC rows key on **CDC Code** (a specific
  Community Diagnostic Centre, e.g. `A3I6U` "Barking Community Hospital CDC"),
  not the DM01 **Provider Org Code**. There is no guaranteed 1:1 mapping
  between a CDC and an NHS provider trust in this file. The canonical schema
  therefore keeps CDC activity as its own fact table keyed on CDC code, joined
  to `providers` only where a mapping can be established — this is
  called out explicitly as a data-quality limitation, not silently forced.
- **Test naming mismatch:** CDC uses full test names ("Magnetic Resonance
  Imaging", "Computed Tomography") where DM01 uses short codes ("MRI", "CT").
  A test-name alias mapping is required (see `docs/data_dictionary.md`).

## 3. National diagnostics time series (context/reference only)

- URL used: `https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/07/Monthly-Diagnostics-Timeseries-May-2026_8BN1G.xls`
- Sheets: `Total Waiting List`, `Total Activity`, `Waiting List Tests`,
  `6+ Week Waits`, `6+ Week Waits %`, `13+ Week Waits`, `Median`,
  `Guidance & Definitions`.
- This is a **national aggregate**, not provider-level — it is not used as a
  primary ingestion source. It may be used as background/context material for
  RAG methodology documents once its structure is worked through (the
  `Guidance & Definitions` sheet did not extract cleanly via `pandas`/`xlrd`
  in initial inspection — likely a text box rather than cell data — so
  official methodology text will instead be sourced from the publication
  page's own guidance links during Step 6).

## 4. Licence

- **Licence:** Open Government Licence v3.0 —
  https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/

**Attribution (used verbatim in the app/README):**

> This project uses publicly accessible aggregate information published by
> NHS England under the Open Government Licence v3.0. The data was cleaned,
> normalized, and transformed for an independent educational project. This
> project is not endorsed by NHS England.

## 5. Transformations performed

- DM01: filtered to the 4 MVP diagnostic groups (`MRI`, `CT`,
  `NON_OBSTETRIC_ULTRASOUND`, `COLONOSCOPY`); aggregated across commissioners
  to provider level (summed per provider/test/period); numeric fields parsed
  and validated (non-negative, `Total WL` reconciled against the sum of the
  13 weekly waiting bands).
- CDC: test-name aliases normalized to DM01's short codes; `Reporting Month`
  (`Mon-YY`) parsed to an ISO reporting period.
- Raw downloaded files are kept immutable under a locally ignored directory;
  all normalization happens in the load step, never by editing source files.
