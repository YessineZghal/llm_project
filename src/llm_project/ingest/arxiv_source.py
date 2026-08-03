"""Fetch paper metadata from the arXiv API (public, no API key required)."""

import time
import xml.etree.ElementTree as ET

import requests

from llm_project.config import ARXIV_CATEGORIES, ARXIV_MAX_RESULTS_PER_TOPIC, ARXIV_TOPICS

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
REQUEST_DELAY_SECONDS = 3  # arXiv's usage policy asks for >=3s between requests


def _build_search_query(topic: str) -> str:
    category_clause = " OR ".join(f"cat:{cat}" for cat in ARXIV_CATEGORIES)
    topic_clause = "+AND+".join(f'all:"{word}"' for word in topic.split())
    return f"({category_clause})+AND+({topic_clause})"


def _parse_entry(entry: ET.Element, topic: str) -> dict:
    arxiv_id = entry.find("atom:id", ATOM_NS).text.strip().split("/abs/")[-1]
    title = entry.find("atom:title", ATOM_NS).text.strip().replace("\n", " ")
    abstract = entry.find("atom:summary", ATOM_NS).text.strip().replace("\n", " ")
    published = entry.find("atom:published", ATOM_NS).text.strip()
    updated = entry.find("atom:updated", ATOM_NS).text.strip()
    authors = [
        author.find("atom:name", ATOM_NS).text.strip()
        for author in entry.findall("atom:author", ATOM_NS)
    ]
    categories = [cat.get("term") for cat in entry.findall("{http://arxiv.org/schemas/atom}category")]
    if not categories:
        categories = [c.get("term") for c in entry.findall("atom:category", ATOM_NS)]
    pdf_url = ""
    abs_url = ""
    for link in entry.findall("atom:link", ATOM_NS):
        if link.get("title") == "pdf":
            pdf_url = link.get("href")
        if link.get("rel") == "alternate":
            abs_url = link.get("href")

    return {
        "id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "categories": categories,
        "published": published,
        "updated": updated,
        "url": abs_url,
        "pdf_url": pdf_url,
        "source_topic": topic,
    }


def fetch_topic(topic: str, max_results: int = ARXIV_MAX_RESULTS_PER_TOPIC) -> list[dict]:
    params = {
        "search_query": _build_search_query(topic),
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    response = requests.get(ARXIV_API_URL, params=params, timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    entries = root.findall("atom:entry", ATOM_NS)
    return [_parse_entry(entry, topic) for entry in entries]


def fetch_all(topics: list[str] | None = None) -> list[dict]:
    topics = topics or ARXIV_TOPICS
    seen_ids: set[str] = set()
    papers: list[dict] = []
    for i, topic in enumerate(topics):
        results = fetch_topic(topic)
        for paper in results:
            if paper["id"] not in seen_ids:
                seen_ids.add(paper["id"])
                papers.append(paper)
        if i < len(topics) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)
    return papers
