"""Unit tests for the grounding check (plan.md Step 13's post-generation
verification that every factual number in an answer traces to evidence).
Pure logic tests with constructed evidence, no LLM/DB access.
"""

from llm_project.rag.grounding import EvidencePackage, check_numeric_grounding


def _evidence(result: dict) -> EvidencePackage:
    return EvidencePackage(tool_results=[{"tool_name": "x", "arguments": {}, "result": result}])


def test_grounded_numbers_pass():
    evidence = _evidence({"total_waiting": 6961, "percentage_waiting_6_plus_weeks": 31.86})
    check = check_numeric_grounding("The waiting list is 6961, with 31.86 percent waiting 6+ weeks.", evidence)
    assert check.fully_grounded
    assert check.total_numbers == 2


def test_rounded_numbers_still_ground():
    evidence = _evidence({"percentage_waiting_6_plus_weeks": 31.86})
    check = check_numeric_grounding("About 31.9 percent are waiting 6+ weeks.", evidence)
    assert check.fully_grounded


def test_fabricated_number_is_caught():
    evidence = _evidence({"total_waiting": 6961})
    check = check_numeric_grounding("The waiting list is 6961, and activity fell by 4500.", evidence)
    assert not check.fully_grounded
    assert 4500.0 in check.ungrounded
    assert check.grounded_numbers == 1


def test_small_numbers_excluded_as_not_factual():
    # "top 5" / "3 months" style small numbers shouldn't count as ungrounded
    # factual claims even with no evidence at all.
    evidence = EvidencePackage()
    check = check_numeric_grounding("Here are the top 5 providers over the last 3 months.", evidence)
    assert check.total_numbers == 0


def test_provider_code_fragments_not_treated_as_numbers():
    evidence = _evidence({"provider_code": "NT322"})
    check = check_numeric_grounding("The provider NT322 has a long waiting list of 42.", evidence)
    # 42 is below the min_value threshold (10 is the default... wait 42 >= 10)
    # 42 has no evidence support and is not a code fragment, so it should be flagged.
    assert 42.0 in check.ungrounded
    # "322" from "NT322" must not appear as its own grounded/ungrounded number.
    assert 322.0 not in check.ungrounded


def test_empty_answer_is_trivially_grounded():
    check = check_numeric_grounding("I don't have enough information to answer that.", EvidencePackage())
    assert check.fully_grounded
    assert check.total_numbers == 0
