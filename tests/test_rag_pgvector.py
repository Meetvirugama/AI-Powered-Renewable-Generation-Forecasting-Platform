"""pgvector integration tests.

The rest of the suite runs on SQLite, which means the dense retrieval SQL that
actually executes in production -- the `<=>` cosine operator, the vector cast,
the ANY(:docs) filter -- is never exercised by it. These tests close that gap.

They are skipped unless TEST_DATABASE_URL points at a reachable PostgreSQL with
the vector extension available. CI sets it (see .github/workflows/ci.yml); on a
laptop, `docker compose up db` is enough:

    TEST_DATABASE_URL=postgresql+psycopg2://renewable:devpassword@localhost:5432/renewable \
        pytest tests/test_rag_pgvector.py -v
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text as sql
from sqlalchemy.orm import sessionmaker

from backend.modules.rag import embed, retriever

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith("postgresql"),
    reason="TEST_DATABASE_URL is not a PostgreSQL URL; pgvector tests skipped",
)

TABLE = "regulation_chunks_pgtest"

CORPUS = [
    (
        "CERC_DSM_Regulations_2024", "Regulation 5(1)", "Tolerance band", 8,
        "The tolerance band for solar generators shall be fifteen percent of available capacity.",
    ),
    (
        "CERC_DSM_Amendment_2026", "Regulation 7(2)(b)", "Deviation charges for sellers", 14,
        "Where actual injection deviates beyond the narrowed tolerance band, deviation "
        "charges shall be payable at the normal rate.",
    ),
    (
        "IEGC_2023", "Clause 6.4", "Frequency bands", 31,
        "When grid frequency falls below 49.85 Hz reserves shall be activated.",
    ),
]


@pytest.fixture(scope="module")
def pg_session():
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as conn:
            conn.execute(sql("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not reachable: {exc}")

    os.environ["RAG_EMBED_BACKEND"] = "mock"
    os.environ["RAG_ENABLE_RERANKER"] = "false"
    embed.reset()

    with engine.begin() as conn:
        try:
            conn.execute(sql("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"pgvector extension unavailable: {exc}")

        # A dedicated table, so these tests never touch a real corpus if someone
        # points TEST_DATABASE_URL at a populated database.
        conn.execute(sql(f"DROP TABLE IF EXISTS {TABLE}"))
        conn.execute(
            sql(
                f"""
                CREATE TABLE {TABLE} (
                    id          BIGSERIAL PRIMARY KEY,
                    doc_name    VARCHAR,
                    section     VARCHAR,
                    clause      VARCHAR,
                    page_no     INT,
                    source_url  TEXT,
                    chunk_text  TEXT,
                    chunk_id    VARCHAR UNIQUE,
                    embedding   VECTOR({embed.EMBED_DIM}),
                    embed_model VARCHAR
                )
                """
            )
        )

        vectors = embed.embed_passages([row[4] for row in CORPUS])
        for (doc, clause, section, page, text), vector in zip(CORPUS, vectors, strict=True):
            conn.execute(
                sql(
                    f"INSERT INTO {TABLE} (doc_name, section, clause, page_no, source_url, "
                    f"chunk_text, chunk_id, embedding, embed_model) VALUES "
                    f"(:doc, :section, :clause, :page, :url, :text, :cid, "
                    f"CAST(:emb AS vector), :model)"
                ),
                {
                    "doc": doc, "section": section, "clause": clause, "page": page,
                    "url": f"https://cercind.gov.in/{doc}.pdf", "text": text,
                    "cid": f"{doc}::{clause}::{page}::0",
                    "emb": "[" + ",".join(f"{float(x):.6f}" for x in vector) + "]",
                    "model": embed.model_name(),
                },
            )

        # The ANN index is built after the rows exist, never before.
        conn.execute(
            sql(
                f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_hnsw ON {TABLE} "
                f"USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
            )
        )

    session = sessionmaker(bind=engine)()
    # The retriever queries `regulation_chunks` by name; point that at the test
    # table for the duration of the module.
    session.execute(sql(f"CREATE OR REPLACE VIEW regulation_chunks AS SELECT * FROM {TABLE}"))
    session.commit()

    yield session

    session.close()
    with engine.begin() as conn:
        conn.execute(sql("DROP VIEW IF EXISTS regulation_chunks"))
        conn.execute(sql(f"DROP TABLE IF EXISTS {TABLE}"))
    retriever.reset_bm25()
    embed.reset()


def test_the_postgres_path_is_the_one_being_exercised(pg_session):
    assert retriever._is_postgres(pg_session) is True


def test_dense_search_runs_the_pgvector_cosine_operator(pg_session):
    """Covers the `<=>` operator and the vector cast, which SQLite cannot run."""
    qv = embed.embed_query("deviation charges normal rate")
    hits = retriever._dense_pg(pg_session, qv, k=3, allowed_docs=None)
    assert hits
    assert all(-1.0 <= h.score <= 1.0 for h in hits), "cosine similarity out of range"
    # Results must come back ordered by distance.
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_dense_search_honours_the_document_filter(pg_session):
    """Covers the ANY(:docs) parameter binding."""
    qv = embed.embed_query("tolerance band")
    hits = retriever._dense_pg(
        pg_session, qv, k=5, allowed_docs={"CERC_DSM_Regulations_2024"}
    )
    assert hits
    assert {h.doc_name for h in hits} == {"CERC_DSM_Regulations_2024"}


def test_hybrid_retrieval_end_to_end_on_postgres(pg_session):
    retriever.build_bm25(pg_session)
    hits = retriever.retrieve(pg_session, "deviation charges tolerance band", k=3)
    assert hits
    citation = hits[0].as_citation()
    assert citation["doc"] and citation["page"]
    assert citation["url"].startswith("https://")


def test_rule_year_filter_works_against_postgres(pg_session):
    retriever.build_bm25(pg_session)
    hits = retriever.retrieve(pg_session, "tolerance band", rule_year=2024, k=5)
    assert hits
    assert "CERC_DSM_Amendment_2026" not in {h.doc_name for h in hits}


def test_stored_embedding_model_is_readable_for_the_startup_check(pg_session):
    report = embed.verify_corpus_model(pg_session, strict=True)
    assert report["live_model"] == embed.model_name()
    assert report["chunks"] == len(CORPUS)


def test_a_corpus_embedded_by_another_model_is_refused(pg_session):
    """The nastiest RAG bug class: no error, just confidently wrong neighbours."""
    pg_session.execute(sql(f"UPDATE {TABLE} SET embed_model = 'some-other-model'"))
    pg_session.commit()
    try:
        with pytest.raises(embed.EmbedModelMismatch):
            embed.verify_corpus_model(pg_session, strict=True)
    finally:
        pg_session.execute(sql(f"UPDATE {TABLE} SET embed_model = :m"), {"m": embed.model_name()})
        pg_session.commit()
