"""Hybrid retrieval: dense (pgvector) + sparse (BM25) -> RRF fusion -> optional rerank.

Why RRF rather than a weighted blend of scores: cosine similarity and BM25 live on
incomparable scales, and calibrating weights between them needs a labelled set we
do not have. Reciprocal Rank Fusion uses rank order only, needs no tuning, and
degrades gracefully when one of the two retrievers returns junk.

Dense search is dialect-aware. On PostgreSQL it pushes the ANN search into
pgvector. On SQLite -- the test suite, and the laptop fallback demo -- embeddings
are stored as TEXT, so the cosine is computed in NumPy over the (small) corpus.
Same ranking, different execution site.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass

import numpy as np
from sqlalchemy import text as sql

from backend.modules.rag import embed

logger = logging.getLogger("renewable_platform")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


TOP_K_DENSE = _int_env("RAG_TOP_K_DENSE", 20)
TOP_K_SPARSE = _int_env("RAG_TOP_K_SPARSE", 20)
TOP_K_FINAL = _int_env("RAG_TOP_K_FINAL", 5)
RRF_K = 60

_FIELDS = ("doc_name", "clause", "section", "page_no", "source_url", "chunk_text")
_YEAR_IN_NAME = re.compile(r"(?:19|20)\d{2}")


def _rerank_enabled() -> bool:
    return os.getenv("RAG_ENABLE_RERANKER", "true").lower() == "true"


@dataclass
class Retrieved:
    chunk_id: int
    doc_name: str
    clause: str
    section: str
    page_no: int
    source_url: str
    chunk_text: str
    score: float

    def as_citation(self) -> dict:
        return {
            "doc": self.doc_name,
            "clause": self.clause or "",
            "section": self.section,
            "page": self.page_no,
            "url": self.source_url or "",
            "snippet": (self.chunk_text or "")[:280],
        }


def _row_to_retrieved(row, score: float) -> Retrieved:
    return Retrieved(chunk_id=row["id"], score=score, **{f: row[f] for f in _FIELDS})


# ------------------------------------------------- BM25 (in memory, built at boot)
_bm25 = None
_bm25_rows: list[dict] = []
_bm25_lock = threading.Lock()
_TOKEN = re.compile(r"[a-z0-9().%]+")


def _tok(s: str) -> list[str]:
    return _TOKEN.findall((s or "").lower())


def build_bm25(session) -> int:
    """Load the corpus into memory for sparse retrieval. ~2k chunks is about 6 MB.

    Called once from the FastAPI lifespan. A missing or empty table is not an
    error: the copilot degrades to dense-only rather than refusing to boot,
    because the same app also serves forecasting routes that have nothing to do
    with RAG.
    """
    global _bm25, _bm25_rows
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.warning("rank_bm25 not installed; sparse retrieval disabled")
        return 0

    try:
        rows = session.execute(
            sql(
                "SELECT id, doc_name, clause, section, page_no, source_url, chunk_text "
                "FROM regulation_chunks ORDER BY id"
            )
        ).mappings().all()
    except Exception as exc:  # noqa: BLE001 - the table may not be migrated yet
        logger.warning("bm25 build skipped: %s", exc)
        return 0

    with _bm25_lock:
        _bm25_rows = [dict(r) for r in rows]
        _bm25 = BM25Okapi([_tok(r["chunk_text"]) for r in _bm25_rows]) if _bm25_rows else None
    logger.info("bm25 index built over %d chunks", len(_bm25_rows))
    return len(_bm25_rows)


def bm25_loaded() -> bool:
    return _bm25 is not None


def reset_bm25() -> None:
    """Drop the in-memory index. Used by tests and after a re-ingest."""
    global _bm25, _bm25_rows
    with _bm25_lock:
        _bm25, _bm25_rows = None, []


def _sparse(query: str, k: int, allowed_docs: set[str] | None) -> list[Retrieved]:
    if _bm25 is None or not _bm25_rows:
        return []
    scores = _bm25.get_scores(_tok(query))
    out: list[Retrieved] = []
    for i in np.argsort(scores)[::-1]:
        if scores[i] <= 0:
            break
        row = _bm25_rows[int(i)]
        if allowed_docs is not None and row["doc_name"] not in allowed_docs:
            continue
        out.append(_row_to_retrieved(row, float(scores[i])))
        if len(out) >= k:
            break
    return out


# --------------------------------------------------------------- dense retrieval
def _is_postgres(session) -> bool:
    try:
        return session.get_bind().dialect.name == "postgresql"
    except Exception:  # noqa: BLE001
        return False


def _parse_embedding(raw) -> np.ndarray | None:
    if raw is None:
        return None
    if isinstance(raw, (list, tuple, np.ndarray)):
        return np.asarray(raw, dtype=np.float32)
    if isinstance(raw, str):
        try:
            return np.asarray(json.loads(raw), dtype=np.float32)
        except (ValueError, TypeError):
            return None
    return None


def _vector_literal(qv: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in qv) + "]"


def _dense_pg(session, qv, k: int, allowed_docs: set[str] | None) -> list[Retrieved]:
    params: dict = {"qv": _vector_literal(qv), "k": k}
    where = "WHERE embedding IS NOT NULL"
    if allowed_docs is not None:
        where += " AND doc_name = ANY(:docs)"
        params["docs"] = list(allowed_docs)
    rows = session.execute(
        sql(
            "SELECT id, doc_name, clause, section, page_no, source_url, chunk_text, "
            "       1 - (embedding <=> CAST(:qv AS vector)) AS score "
            "FROM regulation_chunks "
            + where
            + " ORDER BY embedding <=> CAST(:qv AS vector) LIMIT :k"
        ),
        params,
    ).mappings().all()
    return [_row_to_retrieved(r, float(r["score"])) for r in rows]


def _dense_fallback(session, qv, k: int, allowed_docs: set[str] | None) -> list[Retrieved]:
    """Cosine in NumPy, for backends without pgvector (SQLite tests, laptop demo)."""
    rows = session.execute(
        sql(
            "SELECT id, doc_name, clause, section, page_no, source_url, chunk_text, embedding "
            "FROM regulation_chunks WHERE embedding IS NOT NULL"
        )
    ).mappings().all()

    qn = float(np.linalg.norm(qv)) or 1.0
    scored: list[tuple[float, dict]] = []
    for r in rows:
        if allowed_docs is not None and r["doc_name"] not in allowed_docs:
            continue
        vec = _parse_embedding(r["embedding"])
        if vec is None or vec.shape != qv.shape:
            continue
        denom = (float(np.linalg.norm(vec)) or 1.0) * qn
        scored.append((float(np.dot(vec, qv) / denom), dict(r)))

    scored.sort(key=lambda t: -t[0])
    return [_row_to_retrieved(r, s) for s, r in scored[:k]]


def _dense(session, query: str, k: int, allowed_docs: set[str] | None) -> list[Retrieved]:
    try:
        qv = embed.embed_query(query)
    except Exception as exc:  # noqa: BLE001 - model missing must not kill sparse
        logger.warning("query embedding failed, continuing with sparse only: %s", exc)
        return []
    try:
        if _is_postgres(session):
            return _dense_pg(session, qv, k, allowed_docs)
        return _dense_fallback(session, qv, k, allowed_docs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dense retrieval failed, continuing with sparse only: %s", exc)
        return []


# ------------------------------------------------------------------------ fusion
def rrf(runs: list[list[Retrieved]], k: int = RRF_K) -> list[Retrieved]:
    """Reciprocal Rank Fusion. Rank-only, so the two score scales never have to meet."""
    fused: dict[int, tuple[float, Retrieved]] = {}
    for run in runs:
        for rank, item in enumerate(run, start=1):
            prev_score, prev_item = fused.get(item.chunk_id, (0.0, item))
            fused[item.chunk_id] = (prev_score + 1.0 / (k + rank), prev_item)
    out: list[Retrieved] = []
    for score, item in sorted(fused.values(), key=lambda t: -t[0]):
        item.score = score
        out.append(item)
    return out


# ------------------------------------------------- reranker (optional, never fatal)
_reranker = None
_reranker_lock = threading.Lock()


def _rerank(query: str, cands: list[Retrieved], k: int) -> list[Retrieved]:
    global _reranker
    if not _rerank_enabled() or not cands or embed.backend() == "mock":
        return cands[:k]
    try:
        if _reranker is None:
            with _reranker_lock:
                if _reranker is None:
                    from FlagEmbedding import FlagReranker

                    _reranker = FlagReranker(
                        os.getenv("RAG_RERANK_MODEL", "BAAI/bge-reranker-base"), use_fp16=False
                    )
        scores = _reranker.compute_score([[query, c.chunk_text] for c in cands])
        if isinstance(scores, (int, float)):
            scores = [scores]
        for c, s in zip(cands, scores, strict=False):
            c.score = float(s)
        return sorted(cands, key=lambda c: -c.score)[:k]
    except Exception as exc:  # noqa: BLE001 - a slow or broken reranker must not 500 the copilot
        logger.warning("reranker unavailable, using RRF order: %s", exc)
        return cands[:k]


# ------------------------------------------------------------------- doc filtering
def _doc_year(doc_name: str) -> int | None:
    years = _YEAR_IN_NAME.findall(doc_name or "")
    return max(int(y) for y in years) if years else None


def allowed_docs_for_year(session, rule_year: int | None) -> set[str] | None:
    """Restrict the corpus to documents that already existed in `rule_year`.

    This is what keeps the copilot consistent when a judge drags Member 3's
    regulation slider to 2024: a citation to the 2026 amendment while the UI
    reads 2024 visibly contradicts the demo. The year is read off the document
    name, so adding a PDF to regulations/ needs no code change here.
    """
    if rule_year is None:
        return None
    try:
        names = session.execute(sql("SELECT DISTINCT doc_name FROM regulation_chunks")).scalars().all()
    except Exception:  # noqa: BLE001
        return None
    allowed = {n for n in names if (_doc_year(n) or 0) <= rule_year}
    return allowed or None


def retrieve(session, query: str, *, rule_year: int | None = None, k: int | None = None) -> list[Retrieved]:
    k = k or TOP_K_FINAL
    allowed = allowed_docs_for_year(session, rule_year)
    dense = _dense(session, query, TOP_K_DENSE, allowed)
    sparse = _sparse(query, TOP_K_SPARSE, allowed)
    if not dense and not sparse:
        return []
    fused = rrf([dense, sparse])
    return _rerank(query, fused[: TOP_K_DENSE + TOP_K_SPARSE], k)
