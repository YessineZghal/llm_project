"""Generate a retrieval-evaluation test set: for a sample of indexed papers, ask an LLM
for natural questions that paper's abstract would answer. Ground truth = (doc_id, question).
"""

import csv
import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI
from tqdm import tqdm

from llm_project.config import GROUND_TRUTH_PATH, OPENAI_API_KEY, OPENAI_CHAT_MODEL
from llm_project.search.load_docs import load_docs

GENERATION_PROMPT = """
You are building a test set for a search engine over arXiv paper abstracts.

Given the paper below, write {n} short, natural-language questions a curious researcher
might ask that this abstract answers well. Questions must be answerable from the
abstract alone, must NOT quote the title verbatim, and must NOT say "this paper" or
"this study".

Title: {title}
Abstract: {abstract}

Return a JSON object of the exact form {{"questions": ["...", "..."]}} with exactly
{n} items, nothing else.
""".strip()


def _generate_for_doc(doc: dict, client: OpenAI, n: int) -> list[dict]:
    prompt = GENERATION_PROMPT.format(n=n, title=doc["title"], abstract=doc["abstract"])
    response = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content or "{}")
    questions = data.get("questions", [])
    return [{"doc_id": doc["id"], "question": q} for q in questions[:n]]


def generate_ground_truth(
    sample_size: int = 80,
    questions_per_doc: int = 2,
    seed: int = 42,
    max_workers: int = 8,
) -> list[dict]:
    docs = load_docs()
    rng = random.Random(seed)
    sample = rng.sample(docs, min(sample_size, len(docs)))

    client = OpenAI(api_key=OPENAI_API_KEY)
    rows: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_generate_for_doc, doc, client, questions_per_doc): doc for doc in sample}
        for future in tqdm(as_completed(futures), total=len(futures), desc="generating ground truth"):
            rows.extend(future.result())

    GROUND_TRUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GROUND_TRUTH_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["doc_id", "question"])
        writer.writeheader()
        writer.writerows(rows)

    return rows


if __name__ == "__main__":
    rows = generate_ground_truth()
    print(f"Generated {len(rows)} ground-truth questions -> {GROUND_TRUTH_PATH}")
