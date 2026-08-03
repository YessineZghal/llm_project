"""Grounding evaluation (plan.md Step 13 acceptance gate): "every factual
number in a sample of 50 answers can be matched to a tool result." Runs the
real agent (not mocked) on a real sample of questions and checks each
answer with src/llm_project/rag/grounding.py.
"""

import csv
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import RateLimitError

from llm_project.config import EVAL_DIR
from llm_project.rag.agent import ask_agent
from llm_project.rag.grounding import build_evidence_package, check_numeric_grounding

GROUNDING_EVAL_RESULTS_PATH = EVAL_DIR / "grounding_eval_results.csv"


def _with_retry(fn, *args, max_attempts: int = 5, **kwargs):
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except RateLimitError:
            if attempt == max_attempts - 1:
                raise
            time.sleep(2**attempt)


def _load_questions(sample_size: int, seed: int) -> list[dict]:
    path = EVAL_DIR / "agent_test_cases.jsonl"
    with open(path) as f:
        cases = [json.loads(line) for line in f]
    rng = random.Random(seed)
    return rng.sample(cases, min(sample_size, len(cases)))


def _run_one(case: dict) -> dict:
    result = _with_retry(ask_agent, case["question"])
    evidence = build_evidence_package(result.new_messages)
    check = check_numeric_grounding(result.last_message, evidence)
    return {
        "case_id": case["case_id"],
        "question": case["question"],
        "note": case.get("note", ""),
        "total_numbers": check.total_numbers,
        "grounded_numbers": check.grounded_numbers,
        "fully_grounded": check.fully_grounded,
        "ungrounded": check.ungrounded,
        "answer": result.last_message,
    }


def _warm_up_models() -> None:
    from llm_project.search.embeddings import get_embedder
    from llm_project.search.rerank import get_reranker

    get_embedder()
    get_reranker()


def evaluate_grounding(sample_size: int = 50, seed: int = 7, max_workers: int = 2) -> list[dict]:
    _warm_up_models()
    cases = _load_questions(sample_size, seed)

    results = []
    with open(GROUNDING_EVAL_RESULTS_PATH, "w", newline="") as f:
        fieldnames = ["case_id", "question", "note", "total_numbers", "grounded_numbers", "fully_grounded", "ungrounded"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        f.flush()

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run_one, c): c for c in cases}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                row = {k: v for k, v in result.items() if k != "answer"}
                row["ungrounded"] = ",".join(str(n) for n in row["ungrounded"])
                writer.writerow(row)
                f.flush()

    return results


if __name__ == "__main__":
    results = evaluate_grounding()
    n = len(results)
    fully_grounded = sum(1 for r in results if r["fully_grounded"])
    total_numbers = sum(r["total_numbers"] for r in results)
    grounded_numbers = sum(r["grounded_numbers"] for r in results)

    print(f"Answers evaluated: {n}")
    print(f"Fully grounded (every number verified): {fully_grounded}/{n} ({fully_grounded / n:.1%})")
    if total_numbers:
        print(f"Individual numbers grounded: {grounded_numbers}/{total_numbers} ({grounded_numbers / total_numbers:.1%})")
    print()
    print("Answers with ungrounded numbers:")
    for r in results:
        if not r["fully_grounded"]:
            print(f"  {r['case_id']} ({r['note']}): {r['ungrounded']} - {r['question'][:70]}")
    print(f"\nSaved -> {GROUNDING_EVAL_RESULTS_PATH}")
