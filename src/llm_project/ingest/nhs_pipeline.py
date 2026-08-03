"""Deterministic NHS diagnostics ingestion (plan.md Step 3): download -> hash
-> check-already-ingested -> validate -> normalize (aggregate to provider
level) -> load into the canonical schema (db/nhs_schema.py).

Idempotent: re-running against the same source URL is a no-op once that
file's hash is already recorded in `source_files` (see `_already_ingested`).
Runs standalone:

    uv run python -m llm_project.ingest.nhs_pipeline <dm01_url> [<dm01_url> ...] --cdc <cdc_url>
"""

import argparse
import sys
from collections import defaultdict
from datetime import date

from llm_project.db.models import get_session, init_db
from llm_project.db.nhs_schema import (
    CdcActivityFact,
    DiagnosticActivityFact,
    DiagnosticTest,
    DiagnosticWaitingFact,
    Provider,
    ReportingPeriod,
    SourceFile,
)
from llm_project.ingest.nhs_source import (
    MVP_TEST_CODES,
    WAITING_BAND_FIELDS,
    download,
    parse_cdc_csv,
    parse_dm01_zip,
)

_MONTH_NUMBERS = {
    name: i
    for i, name in enumerate(
        [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ],
        start=1,
    )
}
_MONTH_ABBR_NUMBERS = {name[:3]: num for name, num in _MONTH_NUMBERS.items()}


def parse_dm01_period(period_label: str) -> tuple[str, date]:
    """'DM01-MAY-2026' -> ('2026-05', date(2026, 5, 1))."""
    _, month_name, year = period_label.split("-")
    month_num = _MONTH_NUMBERS[month_name.lower()]
    return f"{year}-{month_num:02d}", date(int(year), month_num, 1)


def parse_cdc_month(raw: str) -> tuple[str, date]:
    """'May-26' -> ('2026-05', date(2026, 5, 1))."""
    month_abbr, yy = raw.split("-")
    month_num = _MONTH_ABBR_NUMBERS[month_abbr.lower()]
    year = 2000 + int(yy)
    return f"{year}-{month_num:02d}", date(year, month_num, 1)


def _already_ingested(session, dataset: str, sha256: str) -> bool:
    return (
        session.query(SourceFile).filter_by(dataset=dataset, sha256=sha256).first()
        is not None
    )


def _ensure_test_dimension(session) -> None:
    from llm_project.ingest.nhs_source import CDC_NAME_TO_TEST_CODE

    alias_by_code = {code: name for name, code in CDC_NAME_TO_TEST_CODE.items()}
    for code in MVP_TEST_CODES:
        session.merge(DiagnosticTest(test_code=code, test_name=code, cdc_alias=alias_by_code[code]))
    session.commit()


def _aggregate_dm01_rows(rows: list[dict]) -> list[dict]:
    """Sum DM01's provider x commissioner x test rows to provider x test
    (plan.md requires provider-level data; commissioner detail is dropped)."""
    grouped: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["provider_code"], row["test_code"])
        agg = grouped.get(key)
        if agg is None:
            agg = {
                "provider_code": row["provider_code"],
                "provider_name": row["provider_name"],
                "test_code": row["test_code"],
                "bands": [0] * len(row["bands"]),
                "total_waiting": 0,
                "waiting_list_activity": 0,
                "planned_activity": 0,
                "unscheduled_activity": 0,
                "total_activity": 0,
                "source_row_count": 0,
            }
            grouped[key] = agg
        agg["bands"] = [a + b for a, b in zip(agg["bands"], row["bands"])]
        agg["total_waiting"] += row["total_waiting"]
        agg["waiting_list_activity"] += row["waiting_list_activity"]
        agg["planned_activity"] += row["planned_activity"]
        agg["unscheduled_activity"] += row["unscheduled_activity"]
        agg["total_activity"] += row["total_activity"]
        agg["source_row_count"] += 1
    return list(grouped.values())


def load_dm01_source(url: str, session) -> dict:
    downloaded = download(url)
    if _already_ingested(session, "dm01", downloaded.sha256):
        return {"url": url, "status": "skipped_already_ingested"}

    raw_rows = parse_dm01_zip(downloaded.content)
    if not raw_rows:
        raise ValueError(f"no MVP-scope rows parsed from {url}")

    period_label = raw_rows[0]["period_label"]
    period_id, period_month = parse_dm01_period(period_label)

    _ensure_test_dimension(session)
    session.merge(ReportingPeriod(period_id=period_id, period_month=period_month, period_label=period_label))
    session.commit()

    source_file = SourceFile(
        dataset="dm01",
        url=url,
        sha256=downloaded.sha256,
        reporting_period_id=period_id,
        row_count=len(raw_rows),
    )
    session.add(source_file)
    session.commit()

    aggregated = _aggregate_dm01_rows(raw_rows)
    for provider_agg in aggregated:
        session.merge(
            Provider(provider_code=provider_agg["provider_code"], provider_name=provider_agg["provider_name"])
        )
    session.commit()

    n_waiting, n_activity = 0, 0
    for agg in aggregated:
        band_kwargs = dict(zip(WAITING_BAND_FIELDS, agg["bands"]))
        session.add(
            DiagnosticWaitingFact(
                provider_code=agg["provider_code"],
                test_code=agg["test_code"],
                period_id=period_id,
                total_waiting=agg["total_waiting"],
                source_file_id=source_file.id,
                source_row_count=agg["source_row_count"],
                **band_kwargs,
            )
        )
        n_waiting += 1
        session.add(
            DiagnosticActivityFact(
                provider_code=agg["provider_code"],
                test_code=agg["test_code"],
                period_id=period_id,
                waiting_list_activity=agg["waiting_list_activity"],
                planned_activity=agg["planned_activity"],
                unscheduled_activity=agg["unscheduled_activity"],
                total_activity=agg["total_activity"],
                source_file_id=source_file.id,
                source_row_count=agg["source_row_count"],
            )
        )
        n_activity += 1
    session.commit()

    return {
        "url": url,
        "status": "loaded",
        "period_id": period_id,
        "raw_rows": len(raw_rows),
        "providers": len({a["provider_code"] for a in aggregated}),
        "waiting_facts": n_waiting,
        "activity_facts": n_activity,
    }


def load_cdc_source(url: str, session) -> dict:
    downloaded = download(url)
    if _already_ingested(session, "cdc", downloaded.sha256):
        return {"url": url, "status": "skipped_already_ingested"}

    rows = parse_cdc_csv(downloaded.content)
    if not rows:
        raise ValueError(f"no MVP-scope rows parsed from {url}")

    _ensure_test_dimension(session)

    periods_seen: dict[str, date] = {}
    for row in rows:
        period_id, period_month = parse_cdc_month(row["reporting_month_raw"])
        row["period_id"] = period_id
        periods_seen[period_id] = period_month
    for period_id, period_month in periods_seen.items():
        session.merge(ReportingPeriod(period_id=period_id, period_month=period_month, period_label=period_id))
    session.commit()

    source_file = SourceFile(dataset="cdc", url=url, sha256=downloaded.sha256, row_count=len(rows))
    session.add(source_file)
    session.commit()

    # dedupe on the fact table's natural grain (cdc_code, test_code, period_id) -
    # the source file can list a CDC/test/month combination at most once, but
    # aggregate defensively in case of any future duplication.
    grouped: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (row["cdc_code"], row["test_code"], row["period_id"])
        agg = grouped.setdefault(key, {**row, "activity_count": 0})
        agg["activity_count"] += row["activity_count"]

    for agg in grouped.values():
        session.add(
            CdcActivityFact(
                cdc_code=agg["cdc_code"],
                cdc_name=agg["cdc_name"],
                region_code=agg["region_code"],
                region_name=agg["region_name"],
                icb=agg["icb"],
                test_code=agg["test_code"],
                period_id=agg["period_id"],
                provider_code=None,  # no CDC->provider mapping available yet, see DATA_SOURCES.md
                activity_count=agg["activity_count"],
                source_file_id=source_file.id,
            )
        )
    session.commit()

    return {
        "url": url,
        "status": "loaded",
        "periods": sorted(periods_seen),
        "raw_rows": len(rows),
        "cdc_facts": len(grouped),
    }


def run(dm01_urls: list[str], cdc_url: str | None = None) -> list[dict]:
    init_db()
    session = get_session()
    results = []
    try:
        for url in dm01_urls:
            results.append(load_dm01_source(url, session))
        if cdc_url:
            results.append(load_cdc_source(cdc_url, session))
    finally:
        session.close()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dm01_urls", nargs="+", help="One or more DM01 monthly ZIP URLs")
    parser.add_argument("--cdc", dest="cdc_url", default=None, help="CDC provider-activity CSV URL")
    args = parser.parse_args()

    for result in run(args.dm01_urls, args.cdc_url):
        print(result)
    sys.exit(0)
