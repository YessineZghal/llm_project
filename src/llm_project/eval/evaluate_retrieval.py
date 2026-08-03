"""Retrieval evaluation: compare every retrieval approach in retriever.METHODS on the
ground-truth set (hit-rate@k and MRR@k), so we pick the best one instead of shipping
whatever we happened to try first.
"""

import csv

from tqdm import tqdm

from llm_project.config import GROUND_TRUTH_PATH, RETRIEVAL_EVAL_RESULTS_PATH
from llm_project.search.retriever import METHODS, retrieve


def _load_ground_truth() -> list[dict]:
    with open(GROUND_TRUTH_PATH) as f:
        return list(csv.DictReader(f))


def evaluate_method(method: str, ground_truth: list[dict], k: int = 5) -> dict:
    hits = 0
    reciprocal_ranks = []

    for row in tqdm(ground_truth, desc=method, leave=False):
        results = retrieve(row["question"], method=method, num_results=k)
        result_ids = [r["id"] for r in results]

        if row["doc_id"] in result_ids:
            hits += 1
            rank = result_ids.index(row["doc_id"]) + 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)

    n = len(ground_truth)
    return {
        "method": method,
        "k": k,
        "num_queries": n,
        "hit_rate": hits / n if n else 0.0,
        "mrr": sum(reciprocal_ranks) / n if n else 0.0,
    }


def evaluate_all(methods: list[str] | None = None, k: int = 5) -> list[dict]:
    methods = methods or METHODS
    ground_truth = _load_ground_truth()

    results = [evaluate_method(method, ground_truth, k=k) for method in methods]
    results.sort(key=lambda r: r["mrr"], reverse=True)

    RETRIEVAL_EVAL_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RETRIEVAL_EVAL_RESULTS_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["method", "k", "num_queries", "hit_rate", "mrr"])
        writer.writeheader()
        writer.writerows(results)

    return results


if __name__ == "__main__":
    results = evaluate_all()
    print(f"{'method':<20} {'hit_rate':>10} {'mrr':>10}")
    for r in results:
        print(f"{r['method']:<20} {r['hit_rate']:>10.3f} {r['mrr']:>10.3f}")
    print(f"\nBest method: {results[0]['method']} (mrr={results[0]['mrr']:.3f})")
    print(f"Saved -> {RETRIEVAL_EVAL_RESULTS_PATH}")
