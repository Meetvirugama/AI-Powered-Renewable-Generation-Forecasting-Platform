"""Embedding layer for the regulation corpus and for live queries.

CRITICAL INVARIANT: the model that embedded the corpus (offline, on a Colab GPU)
and the model that embeds the query (online, on EC2) must be the same. A mismatch
does not raise -- it silently returns plausible-looking but meaningless
neighbours. `verify_corpus_model()` turns that class of bug into a startup error.

Two backends:
  bge  (default) -- BAAI/bge-m3, 1024-dim, the production path.
  mock           -- deterministic hash vectors. Same dimension, same code paths,
                    no 2.2 GB download. Used by the test suite and by CI.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from functools import lru_cache

import numpy as np

logger = logging.getLogger("renewable_platform")

EMBED_DIM = 1024

DEFAULT_MODEL = "BAAI/bge-m3"
MOCK_MODEL_NAME = "mock-hash-1024"

_model = None
_lock = threading.Lock()


# Config is read at call time, not at import time: the offline index build, the
# test suite and the server each select a backend through the environment, and a
# module-level constant would freeze whichever was set first.
def backend() -> str:
    return os.getenv("RAG_EMBED_BACKEND", "bge").lower()


def model_name() -> str:
    """The identifier written to `regulation_chunks.embed_model`."""
    if backend() == "mock":
        return MOCK_MODEL_NAME
    return os.getenv("RAG_EMBED_MODEL", DEFAULT_MODEL)


def dimension() -> int:
    return EMBED_DIM


# ---------------------------------------------------------------- mock backend
def _mock_vectors(texts: list[str]) -> np.ndarray:
    """Deterministic pseudo-embeddings.

    Not semantic -- identical text maps to an identical vector and nothing else
    is guaranteed. That is enough to exercise the SQL, the fusion and the
    guardrail end to end; retrieval *quality* is measured by scripts/eval_retrieval.py
    against the real model.
    """
    out = np.empty((len(texts), EMBED_DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        seed = int.from_bytes(hashlib.sha256(t.encode("utf-8")).digest()[:8], "big")
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(EMBED_DIM).astype(np.float32)
        out[i] = v / (np.linalg.norm(v) or 1.0)
    return out


# ----------------------------------------------------------------- bge backend
def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from FlagEmbedding import BGEM3FlagModel

                name = model_name()
                logger.info("loading embedding model %s (8-15 s)", name)
                # fp16 needs a GPU; EC2 t3.large is CPU-only.
                _model = BGEM3FlagModel(name, use_fp16=False)
    return _model


# -------------------------------------------------------------------- public API
def embed_passages(texts: list[str], batch_size: int = 16) -> np.ndarray:
    """Embed corpus chunks. Used by the offline index build, not by the request path."""
    if not texts:
        return np.empty((0, EMBED_DIM), dtype=np.float32)
    if backend() == "mock":
        return _mock_vectors(texts)
    dense = _get_model().encode(texts, batch_size=batch_size, max_length=1024)["dense_vecs"]
    return np.asarray(dense, dtype=np.float32)


@lru_cache(maxsize=512)
def _embed_query_cached(text: str) -> tuple[float, ...]:
    if backend() == "mock":
        vec = _mock_vectors([text])[0]
    else:
        vec = _get_model().encode([text], max_length=512)["dense_vecs"][0]
    return tuple(float(x) for x in vec)


def embed_query(text: str) -> np.ndarray:
    """Query embedding with an in-process LRU, so a repeated demo question costs 0 ms."""
    return np.asarray(_embed_query_cached(" ".join(text.lower().split())), dtype=np.float32)


def reset() -> None:
    """Drop the loaded model and the query cache. Used by tests that switch backend."""
    global _model
    with _lock:
        _model = None
    _embed_query_cached.cache_clear()


def warmup() -> None:
    """Pay the model load cost at boot instead of on the first user's request.

    Called from the FastAPI lifespan. This is why the container healthcheck uses
    --start-period=90s: a 10 s start period marks a loading container unhealthy
    and Docker restart-loops it forever.
    """
    if backend() == "mock":
        return
    embed_query("warmup")


class EmbedModelMismatch(RuntimeError):
    """The corpus was embedded with a different model than this process queries with."""


def verify_corpus_model(session, *, strict: bool | None = None) -> dict:
    """Compare `embed_model` stored on the corpus against the live model.

    Returns a report. In strict mode (default in prod) a mismatch raises, because
    serving confidently wrong citations is worse than failing to boot.
    """
    from sqlalchemy import text as sql

    if strict is None:
        strict = os.getenv("APP_ENV", "development").lower() in {"prod", "production"}

    rows = session.execute(
        sql(
            "SELECT embed_model, count(*) AS n FROM regulation_chunks "
            "WHERE embedding IS NOT NULL GROUP BY embed_model"
        )
    ).mappings().all()

    stored = {r["embed_model"]: r["n"] for r in rows}
    live = model_name()
    report = {"live_model": live, "corpus_models": stored, "chunks": sum(stored.values())}

    foreign = {m: n for m, n in stored.items() if m != live}
    if foreign:
        msg = (
            f"embed model mismatch: process queries with {live!r} but the corpus holds "
            f"{foreign!r}. Re-run scripts/build_index.py, or set RAG_EMBED_MODEL to match."
        )
        if strict:
            raise EmbedModelMismatch(msg)
        logger.warning(msg)
        report["warning"] = msg
    return report
