import time

from fastapi import APIRouter, HTTPException

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
