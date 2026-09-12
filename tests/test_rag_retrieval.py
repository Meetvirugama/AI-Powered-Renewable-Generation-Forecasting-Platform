"""Hybrid retrieval against a seeded corpus.

These run on the SQLite test database, which has no pgvector, so dense search
takes the NumPy fallback path. That is deliberate: the fallback is also what the
offline laptop demo runs on, so it needs the same test coverage as the pgvector
path rather than less.

Embeddings come from the deterministic mock backend. Ranking *quality* is not
what is asserted here -- that is measured against the real model by
scripts/eval_retrieval.py. What is asserted is the plumbing: fusion, the
rule-year filter, and graceful degradation when half the stack is missing.
"""
import json

import pytest

from backend.db.models import RegulationChunk
from backend.modules.rag import embed, retriever

CORPUS = [
    {
        "doc_name": "CERC_DSM_Regulations_2024",
        "clause": "Regulation 5(1)",
        "section": "Tolerance band",
        "page_no": 8,
        "chunk_text": (
            "The tolerance band for solar generators shall be fifteen percent of the "
            "available capacity, beyond which deviation charges apply."
        ),
    },
    {
        "doc_name": "CERC_DSM_Amendment_2026",
        "clause": "Regulation 7(2)(b)",
        "section": "Deviation charges for sellers",
        "page_no": 14,
        "chunk_text": (
            "Where the actual injection deviates beyond the narrowed tolerance band of "
            "ten percent, deviation charges shall be payable at the normal rate."
        ),
    },
    {
        "doc_name": "IEGC_2023",
        "clause": "Clause 6.4",
        "section": "Frequency bands",
        "page_no": 31,
        "chunk_text": (
            "When grid frequency falls below 49.85 Hz the concerned entities shall "
            "curtail drawal and reserves shall be activated."
        ),
    },
]


@pytest.fixture()
def corpus(db, monkeypatch):
    """Seed the regulation corpus and build the sparse index over it."""
    monkeypatch.setenv("RAG_EMBED_BACKEND", "mock")
    monkeypatch.setenv("RAG_ENABLE_RERANKER", "false")
    embed.reset()

    vectors = embed.embed_passages([c["chunk_text"] for c in CORPUS])
    for row, vector in zip(CORPUS, vectors, strict=False):
        db.add(
            RegulationChunk(
                **row,
                source_url=f"https://cercind.gov.in/{row['doc_name']}.pdf",
                chunk_id=f"{row['doc_name']}::{row['clause']}::{row['page_no']}::0",
                # SQLite stores the vector column as TEXT; the retriever's
                # fallback path parses it back with json.loads.
                embedding=json.dumps([float(x) for x in vector]),
                embed_model=embed.model_name(),
            )
        )
    db.flush()

    retriever.build_bm25(db)
    yield db
    retriever.reset_bm25()
    embed.reset()


# ------------------------------------------------------------------------- fusion
def test_rrf_rewards_agreement_between_the_two_retrievers():
    def item(chunk_id):
        return retriever.Retrieved(
            chunk_id=chunk_id, doc_name="d", clause="c", section="s",
            page_no=1, source_url="", chunk_text="t", score=0.0,
        )

    dense = [item(1), item(2), item(3)]
    sparse = [item(3), item(9)]
    fused = retriever.rrf([dense, sparse])

    # Chunk 3 is the only one both runs returned, so it outranks the item each
    # run ranked first on its own.
    assert fused[0].chunk_id == 3
    assert {f.chunk_id for f in fused} == {1, 2, 3, 9}


def test_rrf_on_no_runs_is_empty():
    assert retriever.rrf([[], []]) == []


# ---------------------------------------------------------------------- retrieval
def test_retrieval_returns_chunks_with_everything_a_citation_needs(corpus):
    hits = retriever.retrieve(corpus, "deviation charges tolerance band", k=3)
    assert hits
    citation = hits[0].as_citation()
    assert citation["doc"] and citation["clause"]
    assert citation["page"] and citation["url"].startswith("https://")
    assert citation["snippet"]


def test_sparse_retrieval_finds_the_clause_by_keyword(corpus):
    """BM25 is the half of the hybrid that must work without a real embedding model."""
    hits = retriever.retrieve(corpus, "frequency falls below 49.85 Hz curtail drawal", k=3)
    assert "IEGC_2023" in {h.doc_name for h in hits}


def test_rule_year_2024_never_cites_the_2026_amendment(corpus):
    """The regulation slider and the citations must agree, or the demo contradicts itself."""
    hits = retriever.retrieve(corpus, "tolerance band for solar generators", rule_year=2024, k=5)
    assert hits
    assert "CERC_DSM_Amendment_2026" not in {h.doc_name for h in hits}


def test_rule_year_2026_can_reach_the_amendment(corpus):
    hits = retriever.retrieve(corpus, "tolerance band for solar generators", rule_year=2026, k=5)
    assert "CERC_DSM_Amendment_2026" in {h.doc_name for h in hits}


def test_no_rule_year_searches_the_whole_corpus(corpus):
    hits = retriever.retrieve(corpus, "deviation", k=5)
    assert len({h.doc_name for h in hits}) >= 2


def test_k_bounds_the_result_count(corpus):
    assert len(retriever.retrieve(corpus, "deviation charges", k=1)) == 1


# -------------------------------------------------------------------- degradation
def test_empty_corpus_returns_nothing_rather_than_raising(db):
    retriever.reset_bm25()
    assert retriever.retrieve(db, "anything at all") == []


def test_build_bm25_on_a_missing_table_is_not_fatal():
    """The forecasting routes must still serve on a database with no RAG corpus.

    Standing in for a database where the RAG migration has not been applied: any
    error reading the table must leave the app bootable.
    """
    retriever.reset_bm25()

    class UnmigratedSession:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError('relation "regulation_chunks" does not exist')

    assert retriever.build_bm25(UnmigratedSession()) == 0
    assert not retriever.bm25_loaded()


def test_dense_failure_leaves_sparse_results_intact(corpus, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("pgvector unavailable")

    monkeypatch.setattr(embed, "embed_query", boom)
    hits = retriever.retrieve(corpus, "deviation charges normal rate", k=3)
    assert hits, "sparse retrieval should still answer when dense is down"


# ------------------------------------------------------------------- doc filtering
@pytest.mark.parametrize(
    "doc_name,expected",
    [
        ("CERC_DSM_Amendment_2026", 2026),
        ("CERC_DSM_Regulations_2024", 2024),
        ("IEGC_2023", 2023),
        ("undated_annexure", None),
    ],
)
def test_document_year_is_read_from_the_filename(doc_name, expected):
    assert retriever._doc_year(doc_name) == expected
