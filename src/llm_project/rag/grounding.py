"""Grounded answer generation support (plan.md Step 13).

Two pieces, deliberately separate from the agent's own prompt instructions
(which only *ask* the model to be grounded - this module *checks* it):

1. `build_evidence_package`: extracts a structured record of everything the
   agent actually used to answer - tool calls and their results, retrieved
   passages, source citations, reporting periods, and data-quality warnings
   - from the agent's raw message trace. This is plan.md's "evidence
   package".
2. `check_numeric_grounding`: a post-generation check that every
   significant number in the final answer actually appears (exactly or
   within a small rounding tolerance) somewhere in that evidence. This is
   plan.md's acceptance gate for this step: "every factual number... can be
   matched to a tool result."

Small numbers (list positions, "top 5", month counts) are excluded by a
minimum-value threshold, since they're not factual claims sourced from data
- they're either request parameters echoed back or structural language.
"""

import json
import re
from dataclasses import dataclass, field


@dataclass
class EvidencePackage:
    tool_results: list[dict] = field(default_factory=list)  # [{tool_name, arguments, result}, ...]
    retrieved_passages: list[dict] = field(default_factory=list)  # [{id, title, abstract}, ...]
    source_urls: list[str] = field(default_factory=list)
    reporting_periods: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        """Flatten every piece of evidence to plain text, for the grounding check."""
        parts = []
        for tr in self.tool_results:
            parts.append(json.dumps(tr.get("result"), default=str))
        for p in self.retrieved_passages:
            parts.append(f"{p.get('title', '')} {p.get('abstract', '')}")
        return " ".join(parts)

    def to_dict(self) -> dict:
        return {
            "tool_results": self.tool_results,
            "retrieved_passages": [
                {"id": p.get("id"), "title": p.get("title")} for p in self.retrieved_passages
            ],
            "source_urls": self.source_urls,
            "reporting_periods": self.reporting_periods,
            "warnings": self.warnings,
        }


def _role(m):
    return m.get("role") if isinstance(m, dict) else getattr(m, "role", None)


def _tool_calls(m):
    calls = getattr(m, "tool_calls", None)
    if calls is None and isinstance(m, dict):
        calls = m.get("tool_calls")
    return calls or []


def build_evidence_package(messages: list) -> EvidencePackage:
    """Args: an agent LoopResult's `new_messages` (or `all_messages`) -
    toyaikit mixes plain dicts and raw OpenAI SDK message objects, handled
    for both here, matching the pattern already used in
    eval/evaluate_agent.py and app/streamlit_app.py."""
    calls_by_id: dict[str, dict] = {}
    for m in messages:
        for tc in _tool_calls(m):
            call_id = getattr(tc, "id", None) or (tc.get("id") if isinstance(tc, dict) else None)
            fn = getattr(tc, "function", None) or (tc.get("function") if isinstance(tc, dict) else None)
            if fn is None or call_id is None:
                continue
            name = getattr(fn, "name", None) or fn.get("name")
            raw_args = getattr(fn, "arguments", None) or fn.get("arguments")
            try:
                args = json.loads(raw_args) if raw_args else {}
            except (TypeError, ValueError):
                args = {}
            calls_by_id[call_id] = {"tool_name": name, "arguments": args}

    tool_results: list[dict] = []
    retrieved_passages: list[dict] = []
    source_urls: list[str] = []
    reporting_periods: list[str] = []
    warnings: list[str] = []

    for m in messages:
        if _role(m) != "tool":
            continue
        call_id = m.get("tool_call_id") if isinstance(m, dict) else getattr(m, "tool_call_id", None)
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        try:
            parsed = json.loads(content) if content else None
        except (TypeError, ValueError):
            parsed = None

        call_info = calls_by_id.get(call_id, {})
        tool_results.append({"tool_name": call_info.get("tool_name"), "arguments": call_info.get("arguments"), "result": parsed})

        if isinstance(parsed, list):
            for doc in parsed:
                if isinstance(doc, dict) and "abstract" in doc:
                    retrieved_passages.append(doc)
                    if doc.get("url"):
                        source_urls.append(doc["url"])
        elif isinstance(parsed, dict):
            if parsed.get("period_id"):
                reporting_periods.append(parsed["period_id"])
            if isinstance(parsed.get("warnings"), list):
                warnings.extend(parsed["warnings"])
            if parsed.get("document_id"):
                retrieved_passages.append({"id": parsed["document_id"], "abstract": parsed.get("definition") or ""})

    return EvidencePackage(
        tool_results=tool_results,
        retrieved_passages=retrieved_passages,
        source_urls=source_urls,
        reporting_periods=sorted(set(reporting_periods)),
        warnings=warnings,
    )


# Negative lookbehind/lookahead exclude digits embedded in alphanumeric
# tokens (provider codes like "NT322") so the check measures standalone
# numeric claims, not code fragments that trivially "ground" against
# themselves.
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])-?\d[\d,]*\.?\d*(?![A-Za-z0-9])")


def _numbers_in(text: str) -> list[float]:
    out = []
    for raw in _NUMBER_RE.findall(text):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def _close(a: float, b: float, abs_tol: float = 0.2, rel_tol: float = 0.01) -> bool:
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


@dataclass
class GroundingCheckResult:
    total_numbers: int
    grounded_numbers: int
    ungrounded: list[float]

    @property
    def grounded_fraction(self) -> float:
        return self.grounded_numbers / self.total_numbers if self.total_numbers else 1.0

    @property
    def fully_grounded(self) -> bool:
        return not self.ungrounded


def check_numeric_grounding(answer_text: str, evidence: EvidencePackage, min_value: float = 10.0) -> GroundingCheckResult:
    """min_value=10 excludes small integers that are typically request
    parameters ("top 5") or structural language ("3 months"), not factual
    claims - the plan.md acceptance gate is about numbers like waiting-list
    counts, percentages, and scores, which are reliably >= 10 in this
    domain (the smallest meaningful percentage/count figures here still
    tend to clear this bar; a genuinely small but factual figure would be
    a rare false negative in this check, not a false pass)."""
    evidence_numbers = _numbers_in(evidence.to_text())
    candidates = [n for n in _numbers_in(answer_text) if abs(n) >= min_value]

    grounded = 0
    ungrounded = []
    for n in candidates:
        if any(_close(n, e) for e in evidence_numbers):
            grounded += 1
        else:
            ungrounded.append(n)

    return GroundingCheckResult(total_numbers=len(candidates), grounded_numbers=grounded, ungrounded=ungrounded)
