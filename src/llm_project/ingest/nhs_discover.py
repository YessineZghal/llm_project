"""Discover the current DM01/CDC file URLs from NHS England's publication
pages, instead of hardcoding one file forever (plan.md section 4 / Step 4
task 1). Verified against the real pages on 2026-08-02 (see DATA_SOURCES.md).
"""

import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from llm_project.ingest.nhs_source import REQUEST_HEADERS

DM01_INDEX_URL_TEMPLATE = (
    "https://www.england.nhs.uk/statistics/statistical-work-areas/"
    "diagnostics-waiting-times-and-activity/monthly-diagnostics-waiting-times-and-activity/"
    "monthly-diagnostics-data-{fiscal_year}/"
)
CDC_INDEX_URL = (
    "https://www.england.nhs.uk/statistics/statistical-work-areas/"
    "diagnostics-waiting-times-and-activity/cdc-management-information/"
)

_DM01_ZIP_RE = re.compile(r"DM01-[A-Z]+-\d{4}-full-extract[^\"'\s]*\.zip$", re.IGNORECASE)


def fiscal_year_slug(today: date | None = None) -> str:
    """UK government fiscal year runs April -> March. 2026-08-02 -> '2026-27';
    2026-02-01 -> '2025-26'."""
    today = today or date.today()
    start_year = today.year if today.month >= 4 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def _fetch_links(url: str) -> list[str]:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return [a["href"] for a in soup.find_all("a", href=True)]


def discover_dm01_urls(fiscal_year: str | None = None) -> list[str]:
    """Every monthly DM01 ZIP linked from the given (or current) fiscal-year
    publication page, in page order (NHS lists most recent first)."""
    fiscal_year = fiscal_year or fiscal_year_slug()
    url = DM01_INDEX_URL_TEMPLATE.format(fiscal_year=fiscal_year)
    links = _fetch_links(url)
    return [href for href in links if _DM01_ZIP_RE.search(href)]


def discover_latest_cdc_url() -> str:
    """The current fiscal year's rolling CDC provider-activity CSV (not the
    historical per-year 'Closedown' archives, which use a different, stable
    naming pattern and aren't what a fresh ingestion run wants)."""
    year = fiscal_year_slug()
    links = _fetch_links(CDC_INDEX_URL)
    candidates = [
        href
        for href in links
        if href.lower().endswith(".csv")
        and f"activity-by-provider-{year}".lower() in href.lower()
        and "closedown" not in href.lower()
    ]
    if not candidates:
        raise ValueError(f"no current-year ({year}) CDC CSV found on {CDC_INDEX_URL}")
    return candidates[0]


if __name__ == "__main__":
    print("fiscal year:", fiscal_year_slug())
    print("DM01 URLs:")
    for u in discover_dm01_urls():
        print(" ", u)
    print("CDC URL:", discover_latest_cdc_url())
