"""Discover the current NHS DM01/CDC files and ingest them. This is the
command the Kestra flow (flows/ingest_diagnostics.yaml) runs on a schedule;
`nhs_pipeline.run()` is idempotent, so re-discovering and re-running against
an already-ingested file is a safe no-op.
"""

from llm_project.ingest.nhs_discover import discover_dm01_urls, discover_latest_cdc_url
from llm_project.ingest.nhs_pipeline import run


def main() -> None:
    dm01_urls = discover_dm01_urls()
    cdc_url = discover_latest_cdc_url()
    print(f"discovered {len(dm01_urls)} DM01 file(s), CDC: {cdc_url}")
    for result in run(dm01_urls, cdc_url):
        print(result)


if __name__ == "__main__":
    main()
