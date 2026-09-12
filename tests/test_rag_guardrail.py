"""The guardrail is the one invariant the project's credibility rests on:
the LLM never originates a number. These tests are the proof, not the prompt.
"""
from dataclasses import dataclass

from backend.modules.rag.guardrail import (
    REDACTION,
    deterministic_fallback,
    enforce,
    validate_citations,
)


@dataclass
class FakeChunk:
    chunk_id: int = 1
    doc_name: str = "CERC_DSM_Amendment_2026"
    clause: str = "Regulation 7(2)(b)"
    section: str = "Deviation charges for sellers"
    page_no: int = 14
    source_url: str = "https://cercind.gov.in/2026/regulation/amendment.pdf"
    chunk_text: str = (
        "Where the actual injection deviates beyond the tolerance band of 10% for "
        "solar generators, deviation charges shall apply at the normal rate."
    )
    score: float = 1.0

    def as_citation(self) -> dict:
        return {
            "doc": self.doc_name,
            "clause": self.clause,
            "section": self.section,
            "page": self.page_no,
            "url": self.source_url,
            "snippet": self.chunk_text[:280],
        }


# --------------------------------------------------------------- number stripping
def test_invented_rupee_figure_is_stripped():
    answer = "The penalty is approximately Rs 25,000 for this block."
    safe, status = enforce(answer, {"penalty_inr": 18240.0}, [])
    assert "25,000" not in safe
    assert REDACTION in safe
    assert status == "numbers_stripped"


def test_engine_figure_survives_in_every_rendering():
    engine = {"penalty_inr": 18240.0, "deviation_pct": -14.2}
    for rendering in ("₹18,240", "Rs 18240", "18,240.00", "INR 18240.0"):
        safe, status = enforce(f"The charge is {rendering} for the block.", engine, [])
        assert status == "pass", rendering
        assert REDACTION not in safe, rendering


def test_negative_percentage_from_engine_survives():
    safe, status = enforce(
        "Actual injection fell 14.2% below the declared schedule.",
        {"deviation_pct": -14.2},
        [],
    )
    assert status == "pass"
    assert "14.2%" in safe


def test_block_numbers_and_years_are_not_stripped():
    safe, status = enforce(
        "Block 52 on 2026 rules sits outside the band described in clause 7.",
        {},
        [],
    )
    assert status == "pass"
    assert "52" in safe and "2026" in safe


def test_small_number_is_still_stripped_when_marked_as_money():
    """A bare 50 is a block number. Rs 50 can only be money, and money must trace
    to the engine even when the figure is small."""
    safe, status = enforce("The charge works out to Rs 50 for the block.", {}, [])
    assert status == "numbers_stripped"
    assert "Rs 50" not in safe


def test_number_quoted_from_a_retrieved_clause_survives():
    safe, status = enforce(
        "Solar generators have a tolerance band of 10% under the amendment.",
        {},
        [FakeChunk()],
    )
    assert status == "pass"
    assert "10%" in safe


def test_no_engine_context_means_no_figures_leave_the_server():
    """The demo moment: ask for a penalty with no engine result behind it."""
    answer = "Your penalty next Tuesday will be around Rs 42,500 based on the trend."
    safe, status = enforce(answer, {}, [])
    assert status == "numbers_stripped"
    assert "42,500" not in safe


def test_empty_answer_is_passed_through():
    assert enforce("", {}, []) == ("", "pass")


# ------------------------------------------------------------ citation validation
def test_invented_citation_is_dropped():
    chunk = FakeChunk()
    answer = "Deviation charges apply. [Imaginary_Reg_2099 | Regulation 99 | p.7]"
    citations = validate_citations(answer, [chunk])
    # No citation matched, so the validator falls back to what was actually
    # retrieved rather than echoing the model's invention.
    assert all(c["doc"] != "Imaginary_Reg_2099" for c in citations)
    assert citations[0]["doc"] == chunk.doc_name


def test_matching_citation_is_kept_with_its_real_url():
    chunk = FakeChunk()
    answer = "Charges apply. [CERC_DSM_Amendment_2026 | Regulation 7(2)(b) | p.14]"
    citations = validate_citations(answer, [chunk])
    assert len(citations) == 1
    assert citations[0]["url"] == chunk.source_url
    assert citations[0]["page"] == 14


def test_citation_matches_on_doc_and_page_when_clause_label_differs():
    chunk = FakeChunk()
    answer = "Charges apply. [CERC_DSM_Amendment_2026 | Reg. 7(2)b | p.14]"
    assert validate_citations(answer, [chunk])[0]["clause"] == chunk.clause


def test_duplicate_citations_are_collapsed():
    chunk = FakeChunk()
    answer = (
        "A. [CERC_DSM_Amendment_2026 | Regulation 7(2)(b) | p.14] "
        "B. [CERC_DSM_Amendment_2026 | Regulation 7(2)(b) | p.14]"
    )
    assert len(validate_citations(answer, [chunk])) == 1


def test_no_retrieval_yields_no_citations():
    assert validate_citations("Some answer with no citation.", []) == []


# ----------------------------------------------------------- deterministic fallback
def test_fallback_states_engine_numbers_and_names_the_provision():
    text = deterministic_fallback(
        "Why was block 52 penalised?",
        {"penalty_inr": 18240.0, "deviation_pct": -14.2},
        [FakeChunk()],
    )
    assert "18,240" in text
    assert "14.2%" in text
    assert "under-injection" in text
    assert "Regulation 7(2)(b)" in text


def test_fallback_survives_the_guardrail_it_feeds():
    """The fallback is the answer served when every provider is down, so it must
    not itself trip the number check."""
    engine = {"penalty_inr": 18240.0, "deviation_pct": -14.2}
    text = deterministic_fallback("Why?", engine, [FakeChunk()])
    _, status = enforce(text, engine, [FakeChunk()])
    assert status == "pass"


def test_fallback_with_no_engine_values_states_no_figures():
    text = deterministic_fallback("What will I owe?", {}, [])
    assert "no figures can be stated" in text
