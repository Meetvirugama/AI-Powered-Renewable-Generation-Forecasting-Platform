"""End-to-end copilot: cache -> retrieve -> generate -> guardrail -> persist.

Runs the real graph with two substitutions that keep it hermetic: the mock
embedding backend (no 2.2 GB download) and the mock LLM provider (no API key, no
network). Every other component -- fusion, the rule-year filter, the guardrail,
citation validation, the cache -- is the production code path.
"""
import json

import pytest

from backend.db.models import RegulationChunk
from backend.modules.rag import cache, copilot, embed, llm, retriever

CORPUS = [
    {
        "doc_name": "CERC_DSM_Regulations_2024",
        "clause": "Regulation 5(1)",
        "section": "Tolerance band",
        "page_no": 8,
        "chunk_text": (
            "The tolerance band for solar generators shall be fifteen percent of "
            "available capacity, beyond which deviation charges become payable."
        ),
    },
    {
        "doc_name": "CERC_DSM_Amendment_2026",
        "clause": "Regulation 7(2)(b)",
        "section": "Deviation charges for sellers",
        "page_no": 14,
        "chunk_text": (
            "Where the actual injection deviates beyond the narrowed tolerance band, "
            "deviation charges shall be payable at the normal rate for the block."
        ),
    },
]

ENGINE_CONTEXT = {
    "penalty_inr": 18240.0,
    "deviation_pct": -14.2,
    "schedule_mw": 42.5,
    "actual_mw": 36.4,
    "rule_version": "CERC_DSM_2026",
}


@pytest.fixture()
def rag_db(db, monkeypatch):
    monkeypatch.setenv("RAG_EMBED_BACKEND", "mock")
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "mock")
    monkeypatch.setenv("RAG_ENABLE_RERANKER", "false")
    embed.reset()
    cache.clear()

    vectors = embed.embed_passages([c["chunk_text"] for c in CORPUS])
    for row, vector in zip(CORPUS, vectors, strict=False):
        db.add(
            RegulationChunk(
                **row,
                source_url=f"https://cercind.gov.in/{row['doc_name']}.pdf",
                chunk_id=f"{row['doc_name']}::{row['clause']}::{row['page_no']}::0",
                embedding=json.dumps([float(x) for x in vector]),
                embed_model=embed.model_name(),
            )
        )
    db.flush()
    retriever.build_bm25(db)

    yield db

    retriever.reset_bm25()
    cache.clear()
    embed.reset()


# ---------------------------------------------------------------- response shape
def test_response_matches_the_frozen_contract(rag_db):
    result = copilot.ask(
        rag_db, "Why was block 52 penalised?", rule_year=2026, engine_context=ENGINE_CONTEXT
    )
    assert set(result) >= {"answer", "citations", "engine_values", "meta"}
    assert set(result["meta"]) >= {
        "llm_model", "cached", "latency_ms", "retrieved_chunks", "guardrail",
    }
    assert result["answer"]
    assert result["meta"]["guardrail"] in {"pass", "numbers_stripped", "fallback_template"}


def test_engine_values_are_echoed_verbatim_never_recomputed(rag_db):
    """The structural half of 'the LLM never computes money': the frontend renders
    rupees from engine_values, which is a copy of the request."""
    result = copilot.ask(rag_db, "Explain the charge.", engine_context=ENGINE_CONTEXT)
    assert result["engine_values"] == ENGINE_CONTEXT
    assert result["engine_values"]["penalty_inr"] == 18240.0


def test_every_citation_points_at_a_chunk_that_was_retrieved(rag_db):
    result = copilot.ask(rag_db, "What are the deviation charges?", rule_year=2026)
    real_docs = {c["doc_name"] for c in CORPUS}
    assert result["citations"]
    for citation in result["citations"]:
        assert citation["doc"] in real_docs
        assert citation["url"].startswith("https://")


def test_retrieved_chunk_count_is_reported(rag_db):
    result = copilot.ask(rag_db, "deviation charges", rule_year=2026)
    assert result["meta"]["retrieved_chunks"] > 0


# --------------------------------------------------------------------- guardrail
def test_question_with_no_engine_context_produces_no_rupee_figure(rag_db):
    """The demo moment: a naive chatbot confabulates a number here."""
    result = copilot.ask(rag_db, "What will my penalty be next Tuesday?")
    assert result["engine_values"] == {}
    assert "₹" not in result["answer"] or "not computed by the engine" in result["answer"]


def test_guardrail_strips_a_figure_the_engine_did_not_produce(rag_db, monkeypatch):
    monkeypatch.setattr(
        llm, "complete", lambda *a, **k: ("The penalty is Rs 25,000 for this block.", "mock")
    )
    result = copilot.ask(rag_db, "How much?", engine_context={"penalty_inr": 18240.0})
    assert "25,000" not in result["answer"]
    assert result["meta"]["guardrail"] == "numbers_stripped"


def test_rule_year_2024_never_cites_the_2026_amendment(rag_db):
    result = copilot.ask(rag_db, "What is the tolerance band?", rule_year=2024)
    assert "CERC_DSM_Amendment_2026" not in {c["doc"] for c in result["citations"]}


# ------------------------------------------------------------------------- cache
def test_second_identical_question_is_served_from_cache(rag_db):
    first = copilot.ask(rag_db, "Why was this block penalised?", engine_context=ENGINE_CONTEXT)
    second = copilot.ask(rag_db, "Why was this block penalised?", engine_context=ENGINE_CONTEXT)
    assert first["meta"]["cached"] is False
    assert second["meta"]["cached"] is True
    assert second["answer"] == first["answer"]


def test_same_question_under_a_different_rule_year_is_a_different_entry(rag_db):
    copilot.ask(rag_db, "What is the tolerance band?", rule_year=2026)
    second = copilot.ask(rag_db, "What is the tolerance band?", rule_year=2024)
    assert second["meta"]["cached"] is False


def test_same_question_with_a_different_penalty_is_a_different_entry(rag_db):
    copilot.ask(rag_db, "Explain this.", engine_context={"penalty_inr": 1000.0})
    second = copilot.ask(rag_db, "Explain this.", engine_context={"penalty_inr": 2000.0})
    assert second["meta"]["cached"] is False


# ------------------------------------------------------------------- degradation
def test_total_provider_outage_still_returns_the_engine_numbers(rag_db, monkeypatch):
    def all_down(*_args, **_kwargs):
        raise llm.AllProvidersFailed("groq and gemini both unreachable")

    monkeypatch.setattr(llm, "complete", all_down)
    result = copilot.ask(rag_db, "Why was block 52 penalised?", engine_context=ENGINE_CONTEXT)

    assert result["meta"]["guardrail"] == "fallback_template"
    assert result["meta"]["llm_model"] == "fallback_template"
    assert "18,240" in result["answer"]          # the figure that matters survives
    assert result["engine_values"] == ENGINE_CONTEXT


def test_a_fallback_answer_is_never_cached(rag_db, monkeypatch):
    """Caching an outage would outlive the outage."""
    def all_down(*_args, **_kwargs):
        raise llm.AllProvidersFailed("down")

    monkeypatch.setattr(llm, "complete", all_down)
    copilot.ask(rag_db, "Why?", engine_context=ENGINE_CONTEXT)
    monkeypatch.undo()
    second = copilot.ask(rag_db, "Why?", engine_context=ENGINE_CONTEXT)
    assert second["meta"]["cached"] is False


def test_empty_corpus_degrades_instead_of_crashing(db, monkeypatch):
    monkeypatch.setenv("RAG_EMBED_BACKEND", "mock")
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "mock")
    embed.reset()
    cache.clear()
    retriever.reset_bm25()

    result = copilot.ask(db, "What is the tolerance band?", engine_context=ENGINE_CONTEXT)
    assert result["answer"]
    assert result["meta"]["retrieved_chunks"] == 0
    cache.clear()


# ---------------------------------------------------------------------- briefing
def test_briefing_pregenerates_every_section(rag_db):
    briefing = copilot.generate_briefing(
        rag_db, "GJ_SOLAR_A", "2026-09-12", {**ENGINE_CONTEXT, "rule_year": 2026}
    )
    assert briefing["plant_id"] == "GJ_SOLAR_A"
    assert briefing["date"] == "2026-09-12"
    assert briefing["generated_at"].endswith("+00:00")
    assert len(briefing["sections"]) == len(copilot.BRIEFING_QUESTIONS)
    for section in briefing["sections"]:
        assert section["question"] and section["answer"]
        assert "guardrail" in section


# ------------------------------------------------------------------ LLM routing
def test_provider_without_an_api_key_is_skipped(monkeypatch):
    """Without this, a missing Gemini key costs a 25 s timeout per request."""
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/llama-3.3-70b-versatile")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "gemini/gemini-1.5-flash")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert llm._candidates() == ["groq/llama-3.3-70b-versatile"]


def test_no_configured_key_raises_rather_than_hanging(monkeypatch):
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/llama-3.3-70b-versatile")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "gemini/gemini-1.5-flash")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(llm.AllProvidersFailed):
        llm.complete([{"role": "user", "content": "hi"}])


def test_mock_provider_cites_the_context_it_was_given(monkeypatch):
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "mock")
    text, model = llm.complete(
        [{"role": "user", "content": "CONTEXT:\n[CERC_DSM_Amendment_2026 | Regulation 7(2)(b) | p.14]\nbody"}]
    )
    assert model == "mock"
    assert "[CERC_DSM_Amendment_2026 | Regulation 7(2)(b) | p.14]" in text


def test_pipeline_runs_identically_without_langgraph(rag_db, monkeypatch):
    """langgraph is an optional dependency. Missing it must change nothing but the
    execution mechanism, so the sequential path is held to the same contract."""
    monkeypatch.setattr(copilot, "_GRAPH_UNAVAILABLE", True)
    monkeypatch.setattr(copilot, "_GRAPH", None)
    cache.clear()

    result = copilot.ask(
        rag_db, "Why was block 52 penalised?", rule_year=2026, engine_context=ENGINE_CONTEXT
    )
    assert set(result) >= {"answer", "citations", "engine_values", "meta"}
    assert result["answer"]
    assert result["engine_values"] == ENGINE_CONTEXT
    assert result["meta"]["retrieved_chunks"] > 0


# ------------------------------------------------------- provider redundancy
def test_identical_primary_and_fallback_is_reported_as_no_failover(monkeypatch):
    """Configuring one model twice gives retries, not failover.

    _candidates() de-duplicates, so the two-provider design collapses to one
    entry. That is a legitimate state when only one provider has a key, but it
    must be visible: a rate-limit then goes straight to the deterministic
    template with nothing in between.
    """
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "gemini/gemini-3.6-flash")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "gemini/gemini-3.6-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    report = llm.health()
    assert report["redundancy"] == "single_provider"
    assert "no failover" in report["warning"]


def test_two_distinct_providers_report_dual_redundancy(monkeypatch):
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/llama-3.3-70b-versatile")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "gemini/gemini-3.6-flash")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    report = llm.health()
    assert report["redundancy"] == "dual_provider"
    assert "warning" not in report


def test_one_key_missing_is_flagged_even_with_distinct_models(monkeypatch):
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/llama-3.3-70b-versatile")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "gemini/gemini-3.6-flash")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    report = llm.health()
    assert report["redundancy"] == "single_provider"
    assert "nowhere to fail over" in report["warning"]


def test_no_keys_at_all_reports_none(monkeypatch):
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/llama-3.3-70b-versatile")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "gemini/gemini-3.6-flash")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert llm.health()["redundancy"] == "none"
