"""Generate the RAG corpus from validated database facts (plan.md Step 6).

Every number in every generated document comes directly from
`provider_test_month_metrics` (itself computed by
`src/llm_project/analytics/metrics.py`, never by a language model) or from
static reference text about the data and methodology. This script makes no
LLM calls. Regenerating overwrites the corpus file in full, so there is no
uncontrolled duplication across runs (plan.md Step 6's acceptance gate).

Produces four document types, per plan.md Step 6:
  A. Provider-test profiles - one per (provider, diagnostic test) with
     loaded data, covering the full loaded reporting window.
  B. Diagnostic-test profiles - one per MVP diagnostic test.
  C. Metric definitions - one per derived metric.
  D. Methodology and data-quality documents.

Run: uv run python -m llm_project.rag.generate_corpus
"""

import json
from collections import defaultdict

from llm_project.config import RAW_DOCS_PATH
from llm_project.db.models import get_session
from llm_project.db.nhs_schema import Provider, ProviderTestMonthMetric, ReportingPeriod

TEST_INFO = {
    "MRI": {
        "name": "Magnetic Resonance Imaging",
        "description": (
            "Magnetic Resonance Imaging uses magnetic fields and radio waves to produce detailed "
            "images of internal body structures, commonly used for imaging the brain, spine, joints, "
            "and soft tissue. It does not use ionising radiation."
        ),
    },
    "CT": {
        "name": "Computed Tomography",
        "description": (
            "Computed Tomography combines a series of X-ray images taken from different angles to "
            "produce cross-sectional images of the body, commonly used for imaging bone, blood "
            "vessels, and internal organs. It uses ionising radiation."
        ),
    },
    "NON_OBSTETRIC_ULTRASOUND": {
        "name": "Non-obstetric ultrasound",
        "description": (
            "Non-obstetric ultrasound uses sound waves to produce images of internal structures such "
            "as the abdomen, pelvis, and soft tissue, excluding pregnancy-related (obstetric) scans, "
            "which are reported separately by NHS England. It does not use ionising radiation."
        ),
    },
    "COLONOSCOPY": {
        "name": "Colonoscopy",
        "description": (
            "Colonoscopy is an endoscopic examination of the large bowel using a flexible camera, "
            "used for investigation and surveillance of the colon and rectum."
        ),
    },
}

COUNTING_RULES = (
    "Counts in this dataset are provider-level totals aggregated from NHS England's published "
    "provider-by-commissioner breakdown (see docs/data_dictionary.md); the commissioner dimension "
    "is summed away to reach a single figure per provider, test, and reporting month. Activity "
    "figures combine waiting-list, planned, and unscheduled activity as published by NHS England."
)


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "not available (no prior month loaded for comparison)"
    return f"{value:+.1f} percent"


def _interpretation(pressure_proxy: float | None, persistent_pressure_months: int) -> str:
    if pressure_proxy is None:
        return (
            "Not enough loaded history to characterize the trend for this provider and test yet."
        )
    if pressure_proxy > 5:
        trend = "the waiting list is growing markedly faster than activity"
    elif pressure_proxy > 0:
        trend = "the waiting list is growing somewhat faster than activity"
    elif pressure_proxy > -5:
        trend = "activity is roughly keeping pace with the waiting list"
    else:
        trend = "activity is growing faster than the waiting list"
    persistence_note = (
        f" This pattern held in {persistent_pressure_months} of the loaded prior months."
        if persistent_pressure_months
        else " This is not a sustained pattern across the loaded prior months."
    )
    return f"Based on the most recent month-over-month change, {trend}.{persistence_note}"


def generate_provider_profiles(session) -> list[dict]:
    metrics = session.query(ProviderTestMonthMetric).all()
    periods = {p.period_id: p for p in session.query(ReportingPeriod).all()}
    providers = {p.provider_code: p for p in session.query(Provider).all()}

    by_provider_test: dict[tuple[str, str], list[ProviderTestMonthMetric]] = defaultdict(list)
    for m in metrics:
        by_provider_test[(m.provider_code, m.test_code)].append(m)

    docs = []
    for (provider_code, test_code), rows in by_provider_test.items():
        rows.sort(key=lambda r: periods[r.period_id].period_month)
        first, last = rows[0], rows[-1]
        provider = providers[provider_code]

        overall_change = (
            (last.total_waiting - first.total_waiting) / first.total_waiting * 100
            if first.total_waiting
            else None
        )
        cdc_note = (
            f"{last.cdc_activity}" if last.cdc_activity is not None
            else "not available (no Community Diagnostic Centre to provider mapping yet)"
        )

        body = (
            f"Provider: {provider.provider_name} ({provider_code})\n"
            f"Diagnostic service: {test_code} ({TEST_INFO[test_code]['name']})\n"
            f"Period: {periods[first.period_id].period_label} to {periods[last.period_id].period_label}\n\n"
            f"The waiting list changed from {first.total_waiting} to {last.total_waiting} "
            f"({_fmt_pct(overall_change)} over the period).\n"
            f"The percentage waiting six weeks or longer changed from "
            f"{first.percentage_waiting_6_plus_weeks:.1f} percent to "
            f"{last.percentage_waiting_6_plus_weeks:.1f} percent.\n"
            f"Most recent month-over-month waiting-list change: {_fmt_pct(last.waiting_list_monthly_change)}.\n"
            f"Most recent month-over-month activity change: {_fmt_pct(last.activity_monthly_change)}.\n"
            f"Total activity in {periods[last.period_id].period_label}: {last.total_activity}.\n"
            f"Community Diagnostic Centre activity: {cdc_note}.\n\n"
            f"Interpretation:\n{_interpretation(last.pressure_proxy, last.persistent_pressure_months)}\n\n"
            f"Limitations:\nThis profile covers only the reporting months currently loaded into the "
            f"system ({periods[first.period_id].period_label} to {periods[last.period_id].period_label}); "
            f"it is not a full historical record. NHS England may revise published figures after release. "
            f"This is an aggregate operational summary, not a clinical or patient-level assessment, and no "
            f"causal claim is made about the reason for any change."
        )

        docs.append(
            {
                "id": f"profile-{provider_code}-{test_code}",
                "title": f"Provider profile: {provider.provider_name} - {test_code}",
                "abstract": body,
                "attribution": provider.provider_name,
                "categories": "provider_profile",
                "source_topic": test_code,
                "url": "",
                "published": f"{first.period_id}_{last.period_id}",
                "document_type": "provider_profile",
                "provider_code": provider_code,
                "diagnostic_test": test_code,
                "period_start": first.period_id,
                "period_end": last.period_id,
                "quality_flag": last.quality_flag,
                "version": "v1",
            }
        )
    return docs


def generate_test_definitions() -> list[dict]:
    docs = []
    for test_code, info in TEST_INFO.items():
        body = (
            f"Diagnostic test: {test_code} ({info['name']})\n\n"
            f"{info['description']}\n\n"
            f"Counting rules:\n{COUNTING_RULES}\n\n"
            f"Scope note: this application reports aggregate provider-level waiting-list and activity "
            f"counts for {info['name']} only; it does not report or infer any individual patient's "
            f"clinical situation, diagnosis, or appointment."
        )
        docs.append(
            {
                "id": f"test-definition-{test_code}",
                "title": f"Diagnostic test definition: {test_code}",
                "abstract": body,
                "attribution": info["name"],
                "categories": "test_definition",
                "source_topic": test_code,
                "url": "https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/",
                "published": "",
                "document_type": "test_definition",
                "provider_code": None,
                "diagnostic_test": test_code,
                "period_start": None,
                "period_end": None,
                "quality_flag": "reference",
                "version": "v1",
            }
        )
    return docs


METRIC_DEFINITIONS = [
    (
        "waiting-six-weeks-or-longer",
        "What does waiting six weeks or longer mean",
        "The percentage waiting six weeks or longer is the proportion of a provider's waiting list, for "
        "a given diagnostic test and reporting month, whose recorded wait has reached six weeks or more "
        "at the point the data was collected. It is computed by summing the published weekly waiting "
        "bands from six-to-seven weeks through thirteen-plus weeks, and dividing by the total waiting "
        "list for that provider, test, and month. It describes the waiting list at a point in time, not "
        "how long any specific patient will ultimately wait.",
    ),
    (
        "total-waiting",
        "What does total waiting mean",
        "Total waiting is the full count of patients on a provider's waiting list for a given diagnostic "
        "test at the end of the reporting month, summed across all thirteen published weekly waiting "
        "bands plus the thirteen-plus-week band. It is a snapshot figure, not a cumulative count of "
        "referrals over time.",
    ),
    (
        "month-over-month-change",
        "What does month-over-month change mean",
        "Month-over-month change is the percentage difference between a provider's figure (waiting list "
        "or activity) in the current reporting month and the same provider's figure in the immediately "
        "preceding loaded reporting month. It is reported as not available, rather than zero, when no "
        "prior month has been loaded for that provider and test.",
    ),
    (
        "pressure-proxy",
        "What does the pressure proxy mean",
        "The pressure proxy is the month-over-month percentage change in a provider's waiting list minus "
        "the month-over-month percentage change in that provider's activity, for a given diagnostic "
        "test. A positive value means the waiting list is growing faster than activity; a negative value "
        "means activity is growing faster than the waiting list. It is a relative indicator, not an "
        "official NHS measure.",
    ),
    (
        "persistent-pressure",
        "What does persistent pressure mean",
        "Persistent pressure is the count of loaded prior reporting months in which a provider's pressure "
        "proxy, for a given diagnostic test, was positive (waiting list growing faster than activity). "
        "It is bounded by how many months are currently loaded into the system and is not a full "
        "historical count.",
    ),
    (
        "bottleneck-score",
        "What does the bottleneck score mean",
        "The bottleneck score is a project-specific composite indicator, not an official NHS metric, "
        "combining five normalized components: long-wait percentage, waiting-list growth, activity "
        "imbalance, persistence, and a Community Diagnostic Centre capacity indicator where available. "
        "Three weighting scenarios are computed - balanced, waiting-focused, and capacity-focused - "
        "weighting the same components differently, so a provider's relative position can be examined "
        "under different assumptions rather than presented as a single authoritative ranking. Components "
        "are normalized to a zero-to-hundred scale within the set of providers reporting the same "
        "diagnostic test and reporting month; a provider's score therefore reflects its position "
        "relative to other providers reporting that test in that month, not an absolute threshold.",
    ),
]


def generate_metric_definitions() -> list[dict]:
    docs = []
    for key, title, body in METRIC_DEFINITIONS:
        docs.append(
            {
                "id": f"metric-{key}",
                "title": title,
                "abstract": body,
                "attribution": "ScanFlow AI methodology",
                "categories": "metric_definition",
                "source_topic": "definitions",
                "url": "",
                "published": "",
                "document_type": "metric_definition",
                "provider_code": None,
                "diagnostic_test": None,
                "period_start": None,
                "period_end": None,
                "quality_flag": "reference",
                "version": "v1",
            }
        )
    return docs


METHODOLOGY_DOCS = [
    (
        "data-sources",
        "Data sources and licence",
        "This application uses NHS England's Monthly Diagnostic Waiting Times and Activity return "
        "(known as DM01) and Community Diagnostic Centre activity data, both published under the Open "
        "Government Licence version 3.0. Exact file URLs, download dates, and content hashes for every "
        "ingested file are recorded in the source_files table and in DATA_SOURCES.md. This project is "
        "not endorsed by NHS England.",
    ),
    (
        "provider-level-aggregation",
        "How provider-level figures are calculated",
        "NHS England publishes DM01 data broken down by provider and commissioner. This application "
        "aggregates that data to provider level by summing all commissioner rows for a given provider, "
        "diagnostic test, and reporting month. Commissioner-level detail is not retained in the "
        "application's fact tables.",
    ),
    (
        "data-limitations",
        "Known data limitations",
        "The reporting window currently loaded into this application is a small number of recent "
        "months; year-over-year comparisons and long-run persistence counts are not available until a "
        "longer history is loaded, and are reported as not available rather than approximated. "
        "Community Diagnostic Centre activity cannot currently be linked to a specific NHS provider, "
        "since the published data does not include that mapping; it is retrievable by centre, region, "
        "and integrated care board instead. NHS England may revise previously published figures; each "
        "ingested file is tracked by its own content hash so a revision is treated as a new source "
        "version rather than silently overwriting prior figures.",
    ),
    (
        "scope-and-non-causal-language",
        "Scope of this application and non-causal language",
        "This application reports aggregate, provider-level operational statistics. It does not provide "
        "clinical advice, individual patient prioritization, diagnosis, or treatment recommendations, and "
        "it does not have access to any patient-level data. Associations described in provider profiles "
        "and bottleneck scores, such as a relationship between Community Diagnostic Centre activity and "
        "waiting-list change, are described as associations, not as causal claims.",
    ),
]


def generate_methodology_docs() -> list[dict]:
    docs = []
    for key, title, body in METHODOLOGY_DOCS:
        docs.append(
            {
                "id": f"methodology-{key}",
                "title": title,
                "abstract": body,
                "attribution": "ScanFlow AI methodology",
                "categories": "methodology",
                "source_topic": "methodology",
                "url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
                "published": "",
                "document_type": "methodology",
                "provider_code": None,
                "diagnostic_test": None,
                "period_start": None,
                "period_end": None,
                "quality_flag": "reference",
                "version": "v1",
            }
        )
    return docs


def build_corpus() -> list[dict]:
    session = get_session()
    try:
        docs = []
        docs.extend(generate_provider_profiles(session))
        docs.extend(generate_test_definitions())
        docs.extend(generate_metric_definitions())
        docs.extend(generate_methodology_docs())
        return docs
    finally:
        session.close()


def main() -> None:
    docs = build_corpus()
    with open(RAW_DOCS_PATH, "w") as f:
        for doc in docs:
            f.write(json.dumps(doc) + "\n")

    by_type: dict[str, int] = defaultdict(int)
    for d in docs:
        by_type[d["document_type"]] += 1
    print(f"wrote {len(docs)} documents -> {RAW_DOCS_PATH}")
    for doc_type, count in sorted(by_type.items()):
        print(f"  {doc_type}: {count}")


if __name__ == "__main__":
    main()
