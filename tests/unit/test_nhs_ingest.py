"""Unit tests for NHS ingestion parsing/normalization (plan.md Step 3/18).

Uses small, deterministic, in-memory fixtures built to match the real DM01/
CDC column layout (see docs/data_dictionary.md) rather than depending on
network access or the real downloaded files.
"""

import io
import zipfile
from datetime import date

import pytest

from llm_project.ingest.nhs_discover import fiscal_year_slug
from llm_project.ingest.nhs_pipeline import _aggregate_dm01_rows, parse_cdc_month, parse_dm01_period
from llm_project.ingest.nhs_source import parse_cdc_csv, parse_dm01_zip

DM01_HEADER = (
    '"Period","Provider Parent Org Code","Provider Parent Name","Provider Org Code","Provider Org Name",'
    '"Commissioner Parent Org Code","Commissioner Parent Name","Commissioner Org Code","Commissioner Org Name",'
    '"Diagnostic Tests Sort Order","Diagnostic Tests",'
    '"00 < 01 Week","01 < 02 Weeks","02 < 03 Weeks","03 < 04 Weeks","04 < 05 Weeks","05 < 06 Weeks",'
    '"06 < 07 Weeks","07 < 08 Weeks","08 < 09 Weeks","09 < 10 Weeks","10 < 11 Weeks","11 < 12 Weeks",'
    '"12 < 13 Weeks","13+ Weeks","Total WL","Waiting List Activity","Planned Activity","Unscheduled Activity","Total Activity"'
)


def _dm01_row(period, provider_code, provider_name, commissioner_code, test, bands, activity):
    total_wl = sum(bands)
    wl_act, planned, unsched = activity
    total_act = wl_act + planned + unsched
    fields = [
        period, "PARENT1", "Parent Trust", provider_code, provider_name,
        "COMM_PARENT", "Commissioner Parent", commissioner_code, "Commissioner Name",
        "1", test,
        *[str(b) for b in bands], str(total_wl), str(wl_act), str(planned), str(unsched), str(total_act),
    ]
    return '"' + '","'.join(fields) + '"'


def _make_dm01_zip(rows: list[str]) -> bytes:
    csv_text = "\n".join([DM01_HEADER, *rows]) + "\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("DM01-MAY-2026-full-extract.csv", csv_text)
    return buf.getvalue()


def test_parse_dm01_zip_filters_to_mvp_tests_and_extracts_fields():
    rows = [
        _dm01_row("DM01-MAY-2026", "PROV1", "Provider One", "COMM1", "MRI",
                  bands=[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], activity=(5, 3, 2)),
        _dm01_row("DM01-MAY-2026", "PROV1", "Provider One", "COMM1", "AUDIOLOGY_ASSESSMENTS",
                  bands=[9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9], activity=(9, 9, 9)),
    ]
    parsed = parse_dm01_zip(_make_dm01_zip(rows))

    assert len(parsed) == 1  # non-MVP test filtered out
    row = parsed[0]
    assert row["provider_code"] == "PROV1"
    assert row["test_code"] == "MRI"
    assert row["total_waiting"] == 14
    assert row["total_activity"] == 10
    assert row["bands"] == [1] * 14


def test_parse_dm01_zip_rejects_total_waiting_mismatch():
    csv_text = "\n".join(
        [
            DM01_HEADER,
            _dm01_row("DM01-MAY-2026", "PROV1", "Provider One", "COMM1", "MRI",
                      bands=[1] * 14, activity=(1, 1, 1)),
        ]
    )
    # corrupt Total WL (2nd-to-last-but-several field) without touching the bands
    csv_text = csv_text.replace('"14","1","1","1","3"', '"999","1","1","1","3"')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("DM01-MAY-2026-full-extract.csv", csv_text + "\n")

    with pytest.raises(ValueError, match="Total WL mismatch"):
        parse_dm01_zip(buf.getvalue())


def test_aggregate_dm01_rows_sums_across_commissioners():
    rows = [
        {
            "provider_code": "PROV1", "provider_name": "Provider One", "test_code": "MRI",
            "bands": [1] * 14, "total_waiting": 14,
            "waiting_list_activity": 5, "planned_activity": 3, "unscheduled_activity": 2, "total_activity": 10,
        },
        {
            "provider_code": "PROV1", "provider_name": "Provider One", "test_code": "MRI",
            "bands": [2] * 14, "total_waiting": 28,
            "waiting_list_activity": 1, "planned_activity": 1, "unscheduled_activity": 1, "total_activity": 3,
        },
    ]
    [agg] = _aggregate_dm01_rows(rows)
    assert agg["provider_code"] == "PROV1"
    assert agg["bands"] == [3] * 14
    assert agg["total_waiting"] == 42
    assert agg["total_activity"] == 13
    assert agg["source_row_count"] == 2


def test_parse_cdc_csv_maps_full_names_to_test_codes():
    csv_text = (
        "Region Code,Regional Name,ICB,CDC Code,CDC Name,ID,Diagnostic Test Type,Reporting Month,Sum of Metric Value\n"
        "Y56,London,North East London ICB,A3I6U,Barking CDC,1,Magnetic Resonance Imaging,May-26,894\n"
        "Y56,London,North East London ICB,A3I6U,Barking CDC,2,Phlebotomy,May-26,1000\n"
    )
    rows = parse_cdc_csv(csv_text.encode("utf-8"))
    assert len(rows) == 1  # "Phlebotomy" isn't an MVP test, filtered out
    assert rows[0]["test_code"] == "MRI"
    assert rows[0]["activity_count"] == 894


@pytest.mark.parametrize(
    "label,expected_period,expected_date",
    [
        ("DM01-MAY-2026", "2026-05", date(2026, 5, 1)),
        ("DM01-MARCH-2026", "2026-03", date(2026, 3, 1)),
    ],
)
def test_parse_dm01_period(label, expected_period, expected_date):
    period_id, period_month = parse_dm01_period(label)
    assert period_id == expected_period
    assert period_month == expected_date


def test_parse_cdc_month():
    period_id, period_month = parse_cdc_month("May-26")
    assert period_id == "2026-05"
    assert period_month == date(2026, 5, 1)


@pytest.mark.parametrize(
    "today,expected",
    [
        (date(2026, 8, 2), "2026-27"),
        (date(2026, 4, 1), "2026-27"),  # fiscal year start boundary
        (date(2026, 3, 31), "2025-26"),  # day before boundary
        (date(2026, 1, 15), "2025-26"),
    ],
)
def test_fiscal_year_slug(today, expected):
    assert fiscal_year_slug(today) == expected
