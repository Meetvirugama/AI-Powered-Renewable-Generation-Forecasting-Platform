"""Contract tests for POST /rag/query.

Member 3 builds the copilot panel against this shape before the real retrieval
exists, so the shape is the thing under test — not the mock's prose.
"""
import pytest

from backend.db.models import RegulationChunk
from backend.schemas.rag import RAGQueryRequest


def test_response_shape_is_stable(client):
    r = client.post("/rag/query", json={
        "question": "Why was block 52 penalised?",
        "plant_id": "GJ_SOLAR_A",
        "block_no": 52,
        "rule_year": 2026,
        "context": {"penalty_inr": 18240.0, "deviation_pct": -14.2},
    })
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"answer", "citations", "engine_values", "meta"}
    assert body["citations"], "an answer with no citation is not shippable"
    for c in body["citations"]:
        assert {"clause", "doc"} <= set(c)
    assert set(body["meta"]) >= {"cached", "guardrail", "retrieved_chunks"}


def test_engine_values_are_echoed_not_recomputed(client):
    """The rupee figure must survive the round trip byte for byte. The copilot
    explains the DSM engine's number; it never produces one of its own."""
    r = client.post("/rag/query", json={
        "question": "Why was block 52 penalised?",
        "context": {"penalty_inr": 18240.0, "deviation_pct": -14.2},
    })
    assert r.json()["engine_values"] == {"penalty_inr": 18240.0, "deviation_pct": -14.2}


def test_rule_year_constrains_cited_documents(client):
    """With the UI slider on 2024, citing the 2026 amendment is a visible
    contradiction in the demo."""
    r = client.post("/rag/query", json={
        "question": "What is the tolerance band?", "rule_year": 2024,
    })
    assert r.status_code == 200
    docs = {c["doc"] for c in r.json()["citations"]}
    assert not any("2026" in d for d in docs), docs


def test_rule_year_out_of_range_is_rejected(client):
    r = client.post("/rag/query", json={"question": "test question", "rule_year": 1999})
    assert r.status_code == 422


def test_blank_question_is_rejected(client):
    r = client.post("/rag/query", json={"question": ""})
    assert r.status_code == 422


def test_request_accepts_optional_fields_only():
    """question is the sole required field; everything else is optional."""
    req = RAGQueryRequest(question="What is DSM?")
    assert req.plant_id is None and req.rule_year is None and req.context is None


def test_regulation_chunk_has_vector_columns():
    """The RAG index needs somewhere to land. Guards against the embedding
    columns being dropped in a future model refactor."""
    cols = RegulationChunk.__table__.columns
    for name in ("embedding", "embed_model", "chunk_id", "chunk_text", "page_no"):
        assert name in cols, f"regulation_chunks.{name} is missing"


def test_chunk_id_is_unique():
    """Re-running the offline ingest must not duplicate the corpus.

    Uses its own engine rather than the shared `db` fixture: the expected
    IntegrityError would otherwise poison that fixture's outer transaction.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from backend.db.models import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as s:
        s.add(RegulationChunk(doc_name="D", chunk_text="x", chunk_id="dup-1"))
        s.commit()
        s.add(RegulationChunk(doc_name="D", chunk_text="y", chunk_id="dup-1"))
        with pytest.raises(IntegrityError):
            s.commit()
