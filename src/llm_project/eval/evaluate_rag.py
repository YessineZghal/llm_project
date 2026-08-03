"""LLM evaluation: compare the two answer-prompt variants in rag/prompts.py using an
LLM-as-judge rubric (relevance, groundedness, clarity), so we pick the best one instead
of evaluating just a single approach.

Retrieval (which touches the sentence-transformers/torch singletons) is done
sequentially first and cached per question — concurrent calls into torch from multiple
threads segfaults on this stack, and each question only needs retrieving once since
both prompt variants reuse the same retrieved docs. Only the OpenAI calls (answer
generation + judging), which are pure network I/O, run in a thread pool.
"""

import csv
import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI
from tqdm import tqdm

from llm_project.config import (
    GROUND_TRUTH_PATH,
    OPENAI_API_KEY,
    OPENAI_CHAT_MODEL,
    OPENAI_JUDGE_MODEL,
    RAG_EVAL_RESULTS_PATH,
)
from llm_project.rag.prompts import PROMPT_VARIANTS, build_context, build_prompt
from llm_project.rag.query_rewrite import rewrite_query
from llm_project.search.retriever import retrieve

JUDGE_PROMPT = """
You are evaluating an AI-generated answer to a research question, given the CONTEXT it
was allowed to use.

QUESTION: {question}

CONTEXT (paper abstracts the model could see):
{context}

ANSWER:
{answer}

Rate the ANSWER from 1 (bad) to 5 (excellent) on:
- relevance: does it directly address the QUESTION?
- groundedness: is every claim supported by CONTEXT, with no invented facts?
- clarity: is it clear, well-organized, and appropriately concise?

Return ONLY a JSON object of the exact form:
{{"relevance": <1-5>, "groundedness": <1-5>, "clarity": <1-5>, "overall": <1-5>}}
""".strip()


def judge_answer(question: str, context: str, answer: str, client: OpenAI) -> dict:
    prompt = JUDGE_PROMPT.format(question=question, context=context, answer=answer)
    response = client.chat.completions.create(
        model=OPENAI_JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content or "{}")


def _generate_and_judge(question: str, variant: str, docs: list[dict], client: OpenAI) -> dict:
    prompt = build_prompt(question, docs, variant=variant)
    response = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    answer = (response.choices[0].message.content or "").strip()

    context = build_context(docs)
    judgment = judge_answer(question, context, answer, client)

    return {
        "variant": variant,
        "question": question,
        "answer": answer,
        "relevance": judgment.get("relevance"),
        "groundedness": judgment.get("groundedness"),
        "clarity": judgment.get("clarity"),
        "overall": judgment.get("overall"),
    }


def evaluate_rag(
    sample_size: int = 25,
    variants: tuple[str, ...] = tuple(PROMPT_VARIANTS.keys()),
    method: str = "es_hybrid_rerank",
    seed: int = 42,
    max_workers: int = 8,
) -> list[dict]:
    with open(GROUND_TRUTH_PATH) as f:
        ground_truth = list(csv.DictReader(f))

    rng = random.Random(seed)
    questions = [row["question"] for row in rng.sample(ground_truth, min(sample_size, len(ground_truth)))]

    client = OpenAI(api_key=OPENAI_API_KEY)

    docs_by_question: dict[str, list[dict]] = {}
    for question in tqdm(questions, desc="retrieving (sequential)"):
        search_query = rewrite_query(question, client=client)
        docs_by_question[question] = retrieve(search_query, method=method, num_results=5)

    jobs = [(q, v) for v in variants for q in questions]
    rows: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_generate_and_judge, q, v, docs_by_question[q], client): (q, v) for q, v in jobs
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="generating + judging"):
            rows.append(future.result())

    RAG_EVAL_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAG_EVAL_RESULTS_PATH, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["variant", "question", "answer", "relevance", "groundedness", "clarity", "overall"]
        )
        writer.writeheader()
        writer.writerows(rows)

    return rows


def summarize(rows: list[dict]) -> list[dict]:
    by_variant: dict[str, list[dict]] = {}
    for row in rows:
        by_variant.setdefault(row["variant"], []).append(row)

    summary = []
    for variant, variant_rows in by_variant.items():
        n = len(variant_rows)
        summary.append(
            {
                "variant": variant,
                "n": n,
                "relevance": sum(r["relevance"] for r in variant_rows) / n,
                "groundedness": sum(r["groundedness"] for r in variant_rows) / n,
                "clarity": sum(r["clarity"] for r in variant_rows) / n,
                "overall": sum(r["overall"] for r in variant_rows) / n,
            }
        )
    summary.sort(key=lambda s: s["overall"], reverse=True)
    return summary


if __name__ == "__main__":
    rows = evaluate_rag()
    summary = summarize(rows)
    print(f"{'variant':<10} {'relevance':>10} {'groundedness':>13} {'clarity':>8} {'overall':>8}")
    for s in summary:
        print(f"{s['variant']:<10} {s['relevance']:>10.2f} {s['groundedness']:>13.2f} {s['clarity']:>8.2f} {s['overall']:>8.2f}")
    print(f"\nBest prompt variant: {summary[0]['variant']} (overall={summary[0]['overall']:.2f})")
    print(f"Saved -> {RAG_EVAL_RESULTS_PATH}")
