"""Automated ingestion pipeline: arXiv API -> dlt -> duckdb -> data/raw/papers.jsonl.

dlt handles dedup/merge-on-id and incremental loads into a local duckdb dataset;
we then materialize that dataset as JSONL for the retrieval layer to consume.
Runs standalone (`uv run python -m llm_project.ingest.pipeline`) or from the
Kestra flow in flows/ingest_arxiv.yaml.
"""

import json

import dlt

from llm_project.config import DATA_DIR, RAW_DOCS_PATH
from llm_project.ingest.arxiv_source import fetch_all

DUCKDB_PATH = DATA_DIR / "arxiv_ingest.duckdb"


@dlt.resource(name="papers", write_disposition="merge", primary_key="id")
def papers_resource():
    for paper in fetch_all():
        yield {
            **paper,
            "authors": ", ".join(paper["authors"]),
            "categories": ", ".join(paper["categories"]),
        }


def run_pipeline() -> int:
    pipeline = dlt.pipeline(
        pipeline_name="arxiv_ingest",
        destination=dlt.destinations.duckdb(str(DUCKDB_PATH)),
        dataset_name="arxiv_papers",
    )
    pipeline.run(papers_resource())

    rows = pipeline.dataset()["papers"].df().to_dict(orient="records")
    with open(RAW_DOCS_PATH, "w") as f:
        for row in rows:
            record = {
                "id": row["id"],
                "title": row["title"],
                "abstract": row["abstract"],
                "authors": row["authors"],
                "categories": row["categories"],
                "published": str(row["published"]),
                "updated": str(row["updated"]),
                "url": row["url"],
                "pdf_url": row["pdf_url"],
                "source_topic": row["source_topic"],
            }
            f.write(json.dumps(record) + "\n")

    return len(rows)


if __name__ == "__main__":
    n = run_pipeline()
    print(f"Ingested {n} papers -> {RAW_DOCS_PATH}")
