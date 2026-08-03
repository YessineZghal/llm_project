"""Download and parse NHS England's DM01 (monthly diagnostics) and CDC
(Community Diagnostic Centre) activity files.

Grounded in the real files inspected during Step 1 (see DATA_SOURCES.md,
docs/data_dictionary.md) — column names and the alias mapping below were
read off the actual downloaded CSVs, not guessed from documentation.
"""

import csv
import hashlib
import io
import zipfile
from dataclasses import dataclass

import requests

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (ScanFlow AI research project; educational use)"}

# MVP scope (plan.md section 3.1): 4 diagnostic groups only.
# DM01 code -> CDC's full test name (verified from the real CDC file's
# `Diagnostic Test Type` column, which uses different vocabulary than DM01).
MVP_TEST_CODES = {
    "MRI": "Magnetic Resonance Imaging",
    "CT": "Computed Tomography",
    "NON_OBSTETRIC_ULTRASOUND": "Non-obstetric Ultrasound",
    "COLONOSCOPY": "Colonoscopy",
}
CDC_NAME_TO_TEST_CODE = {v: k for k, v in MVP_TEST_CODES.items()}

WAITING_BAND_COLUMNS = [
    "00 < 01 Week",
    "01 < 02 Weeks",
    "02 < 03 Weeks",
    "03 < 04 Weeks",
    "04 < 05 Weeks",
    "05 < 06 Weeks",
    "06 < 07 Weeks",
    "07 < 08 Weeks",
    "08 < 09 Weeks",
    "09 < 10 Weeks",
    "10 < 11 Weeks",
    "11 < 12 Weeks",
    "12 < 13 Weeks",
    "13+ Weeks",
]
# model field name for each band column, in the same order
WAITING_BAND_FIELDS = [
    "week_00_01", "week_01_02", "week_02_03", "week_03_04", "week_04_05",
    "week_05_06", "week_06_07", "week_07_08", "week_08_09", "week_09_10",
    "week_10_11", "week_11_12", "week_12_13", "week_13_plus",
]


@dataclass
class DownloadedFile:
    url: str
    content: bytes
    sha256: str


def download(url: str) -> DownloadedFile:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
    response.raise_for_status()
    content = response.content
    return DownloadedFile(url=url, content=content, sha256=hashlib.sha256(content).hexdigest())


def parse_dm01_zip(content: bytes) -> list[dict]:
    """Extract the single CSV inside a DM01 ZIP and return rows filtered to
    the MVP diagnostic groups. Raises if a row's Total WL doesn't reconcile
    with the sum of its own weekly bands (fail closed, per plan.md Step 3)."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(f"expected exactly one CSV in DM01 zip, found {csv_names}")
        raw = zf.read(csv_names[0]).decode("utf-8-sig")

    rows = []
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        test_code = row["Diagnostic Tests"]
        if test_code not in MVP_TEST_CODES:
            continue

        bands = [int(row[col]) for col in WAITING_BAND_COLUMNS]
        total_waiting = int(row["Total WL"])
        if sum(bands) != total_waiting:
            raise ValueError(
                f"Total WL mismatch for {row['Provider Org Code']}/{test_code}: "
                f"sum(bands)={sum(bands)} != Total WL={total_waiting}"
            )

        waiting_list_activity = int(row["Waiting List Activity"])
        planned_activity = int(row["Planned Activity"])
        unscheduled_activity = int(row["Unscheduled Activity"])
        total_activity = int(row["Total Activity"])
        if waiting_list_activity + planned_activity + unscheduled_activity != total_activity:
            raise ValueError(
                f"Total Activity mismatch for {row['Provider Org Code']}/{test_code}"
            )

        rows.append(
            {
                "period_label": row["Period"],
                "provider_code": row["Provider Org Code"],
                "provider_name": row["Provider Org Name"],
                "test_code": test_code,
                "bands": bands,
                "total_waiting": total_waiting,
                "waiting_list_activity": waiting_list_activity,
                "planned_activity": planned_activity,
                "unscheduled_activity": unscheduled_activity,
                "total_activity": total_activity,
            }
        )
    return rows


def parse_cdc_csv(content: bytes) -> list[dict]:
    """Parse the CDC provider-activity CSV, filtered to the MVP tests via the
    CDC_NAME_TO_TEST_CODE alias map. `Reporting Month` stays as the raw
    `Mon-YY` string here; the pipeline resolves it to an ISO period."""
    raw = content.decode("utf-8-sig")
    rows = []
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        test_code = CDC_NAME_TO_TEST_CODE.get(row["Diagnostic Test Type"])
        if test_code is None:
            continue
        rows.append(
            {
                "cdc_code": row["CDC Code"],
                "cdc_name": row["CDC Name"],
                "region_code": row["Region Code"],
                "region_name": row["Regional Name"],
                "icb": row["ICB"],
                "test_code": test_code,
                "reporting_month_raw": row["Reporting Month"],
                "activity_count": int(row["Sum of Metric Value"]),
            }
        )
    return rows
