"""Retrieval evaluation (plan.md Step 8): compare every retrieval approach in
retriever.METHODS on the ground-truth set, computing Hit Rate@5, MRR, Recall@5,
Recall@10, and NDCG@5, so the best approach is selected by measurement, not
intuition. Unanswerable questions are scored separately (a well-behaved
retriever should not return a confident top-1 hit for a question with no
correct document), not folded into the ranking metrics, which assume a real
relevant document exists.
"""

import json
import math

from tqdm import tqdm

from llm_project.config import GROUND_TRUTH_PATH, RETRIEVAL_ERROR_ANALYSIS_PATH, RETRIEVAL_EVAL_RESULTS_PATH
from llm_project.search.retriever import METHODS, retrieve


def _load_ground_truth() -> list[dict]:
    with open(GROUND_TRUTH_PATH) as f:
        return [json.loads(line) for line in f]


def _ndcg_at_k(result_ids: list[str], relevant_ids: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(rank + 2) for rank, doc_id in enumerate(result_ids[:k]) if doc_id in relevant_ids)
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(rank + 2) for rank in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


def evaluate_method(method: str, answerable_rows: list[dict], k: int = 5) -> dict:
    hits = 0
    reciprocal_ranks, recall_5, recall_10, ndcg_5 = [], [], [], []
    errors: list[dict] = []

    for row in tqdm(answerable_rows, desc=method, leave=False):
        relevant = set(row["relevant_document_ids"])
        results_10 = retrieve(row["question"], method=method, num_results=10)
        result_ids = [r["id"] for r in results_10]
        result_ids_5 = result_ids[:5]

        hit = bool(relevant & set(result_ids_5))
        if hit:
            hits += 1
            rank = next(i for i, d in enumerate(result_ids_5) if d in relevant) + 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)
            errors.append(
                {
                    "question_id": row["question_id"],
                    "question": row["question"],
                    "document_type": row["document_type"],
                    "expected": sorted(relevant),
                    "got_top_5": result_ids_5,
                }
            )

        recall_5.append(1.0 if relevant & set(result_ids_5) else 0.0)
        recall_10.append(1.0 if relevant & set(result_ids) else 0.0)
        ndcg_5.append(_ndcg_at_k(result_ids_5, relevant, 5))

    n = len(answerable_rows)
    return {
        "method": method,
        "k": k,
        "num_queries": n,
        "hit_rate": hits / n if n else 0.0,
        "mrr": sum(reciprocal_ranks) / n if n else 0.0,
        "recall_at_5": sum(recall_5) / n if n else 0.0,
        "recall_at_10": sum(recall_10) / n if n else 0.0,
        "ndcg_at_5": sum(ndcg_5) / n if n else 0.0,
        "_errors": errors,
    }


def evaluate_unanswerable(method: str, unanswerable_rows: list[dict]) -> dict:
    """A well-behaved retriever's top score for a genuinely unanswerable
    question should be low relative to its scores on real questions - this
    doesn't feed the ranking metrics above (there's no correct document to
    rank), it's a separate signal for Milestone 6's refusal-behavior work."""
    if not unanswerable_rows:
        return {"method": method, "num_unanswerable": 0}
    returned_nonempty = sum(
        1 for row in unanswerable_rows if retrieve(row["question"], method=method, num_results=1)
    )
    return {
        "method": method,
        "num_unanswerable": len(unanswerable_rows),
        "fraction_returning_a_result": returned_nonempty / len(unanswerable_rows),
    }


def evaluate_all(methods: list[str] | None = None, k: int = 5) -> tuple[list[dict], dict[str, list[dict]]]:
    methods = methods or METHODS
    ground_truth = _load_ground_truth()
    answerable = [r for r in ground_truth if r["answerable"]]
    unanswerable = [r for r in ground_truth if not r["answerable"]]

    results = []
    errors_by_method: dict[str, list[dict]] = {}
    for method in methods:
        result = evaluate_method(method, answerable, k=k)
        errors_by_method[method] = result.pop("_errors")
        result.update(evaluate_unanswerable(method, unanswerable))
        results.append(result)

    results.sort(key=lambda r: r["mrr"], reverse=True)

    RETRIEVAL_EVAL_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    import csv

    fieldnames = [
        "method", "k", "num_queries", "hit_rate", "mrr", "recall_at_5", "recall_at_10",
        "ndcg_at_5", "num_unanswerable", "fraction_returning_a_result",
    ]
    with open(RETRIEVAL_EVAL_RESULTS_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    _write_error_analysis(results, errors_by_method)

    return results, errors_by_method


def _write_error_analysis(results: list[dict], errors_by_method: dict[str, list[dict]]) -> None:
    best_method = results[0]["method"]
    errors = errors_by_method[best_method]

    by_type: dict[str, int] = {}
    for e in errors:
        by_type[e["document_type"]] = by_type.get(e["document_type"], 0) + 1

    lines = [
        "# Retrieval error analysis",
        "",
        f"Best method by MRR: **{best_method}** ({len(errors)} misses out of "
        f"{results[0]['num_queries']} answerable questions).",
        "",
        "## Misses by question category",
        "",
    ]
    for doc_type, count in sorted(by_type.items(), key=lambda x: -x[1]):
        lines.append(f"- {doc_type}: {count}")
    lines.append("")
    lines.append("## Individual misses")
    lines.append("")
    for e in errors:
        lines.append(f"### {e['question_id']} ({e['document_type']})")
        lines.append(f"- Question: {e['question']}")
        lines.append(f"- Expected: {e['expected']}")
        lines.append(f"- Retrieved top 5: {e['got_top_5']}")
        lines.append("")

    with open(RETRIEVAL_ERROR_ANALYSIS_PATH, "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    results, errors_by_method = evaluate_all()
    print(
        f"{'method':<18} {'hit_rate':>9} {'mrr':>7} {'recall@5':>9} "
        f"{'recall@10':>10} {'ndcg@5':>7} {'unanswerable_fp':>16}"
    )
    for r in results:
        print(
            f"{r['method']:<18} {r['hit_rate']:>9.3f} {r['mrr']:>7.3f} {r['recall_at_5']:>9.3f} "
            f"{r['recall_at_10']:>10.3f} {r['ndcg_at_5']:>7.3f} {r['fraction_returning_a_result']:>16.3f}"
        )
    best = results[0]
    print(f"\nBest method: {best['method']} (mrr={best['mrr']:.3f})")
    print(f"Total errors for best method: {len(errors_by_method[best['method']])}")
    print(f"Saved -> {RETRIEVAL_EVAL_RESULTS_PATH}")
    print(f"Error analysis -> {RETRIEVAL_ERROR_ANALYSIS_PATH}")
