import os
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.modules.factory import get_rag_copilot
from backend.schemas.rag import Citation, RAGMeta, RAGQueryRequest, RAGQueryResponse

router = APIRouter(prefix="/rag", tags=["RAG Copilot"])


@router.post("/query", response_model=RAGQueryResponse)
def query_rag_copilot(request: RAGQueryRequest):
    started = time.perf_counter()
    copilot = get_rag_copilot()
    try:
        result = copilot.query(
            question=request.question,
            plant_id=request.plant_id,
            block_no=request.block_no,
            rule_year=request.rule_year,
            context=request.context,
        )
    except Exception as exc:  # noqa: BLE001 - a dead LLM provider is 502, not 500
        raise HTTPException(status_code=502, detail=f"copilot_unavailable: {exc}")

    citations = [
        Citation(
            clause=c["clause"],
            page=c.get("page"),
            doc=c["doc"],
            url=c.get("url", ""),
            section=c.get("section"),
            snippet=c.get("snippet"),
        )
        for c in result.get("citations", [])
    ]

    meta = RAGMeta(**result.get("meta", {}))
    if meta.latency_ms is None:
        meta.latency_ms = int((time.perf_counter() - started) * 1000)

    return RAGQueryResponse(
        answer=result["answer"],
        citations=citations,
        # Echoed back from the request context. The copilot is an explainer:
        # every rupee figure originates in the deterministic DSM engine.
        engine_values=result.get("engine_values"),
        meta=meta,
    )


@router.get("/health")
def rag_health(db: Session = Depends(get_db)):
    """Corpus and provider readiness.

    Worth checking before a demo rather than during one: it surfaces an empty
    corpus, an embed-model mismatch between the index and this process, and a
    missing LLM API key, each of which produces confident nonsense rather than
    an obvious error.
    """
    from backend.modules.rag import cache, llm, retriever

    report = {
        "copilot_type": os.getenv("RAG_COPILOT_TYPE", "mock").lower(),
        "chunks": 0,
        "embed_models": [],
        "bm25_loaded": retriever.bm25_loaded(),
        "cache": cache.stats(),
        "llm": llm.health(),
    }

    try:
        report["chunks"] = db.execute(sql("SELECT count(*) FROM regulation_chunks")).scalar_one()
        report["embed_models"] = [
            m
            for m in db.execute(
                sql("SELECT DISTINCT embed_model FROM regulation_chunks WHERE embed_model IS NOT NULL")
            ).scalars().all()
        ]
    except Exception as exc:  # noqa: BLE001 - report the problem, do not 500 a health check
        report["corpus_error"] = str(exc)

    if report["copilot_type"] == "production":
        from backend.modules.rag import embed

        live = embed.model_name()
        report["live_embed_model"] = live
        mismatched = [m for m in report["embed_models"] if m != live]
        if mismatched:
            report["warning"] = (
                f"corpus embedded with {mismatched} but queries use {live!r}; "
                "retrieval results are meaningless until the index is rebuilt"
            )

    return report
