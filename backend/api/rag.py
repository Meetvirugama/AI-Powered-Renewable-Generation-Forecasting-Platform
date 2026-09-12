from fastapi import APIRouter
from backend.modules.factory import get_rag_copilot
from backend.schemas.rag import RAGQueryRequest, RAGQueryResponse, Citation

router = APIRouter(prefix="/rag", tags=["RAG Copilot"])

@router.post("/query", response_model=RAGQueryResponse)
def query_rag_copilot(request: RAGQueryRequest):
    copilot = get_rag_copilot()
    result = copilot.query(
        question=request.question,
        plant_id=request.plant_id,
        block_no=request.block_no,
        context=request.context,
    )
    citations = [
        Citation(
            clause=c["clause"],
            page=c.get("page"),
            doc=c["doc"],
            url=c.get("url", ""),
        )
        for c in result.get("citations", [])
    ]
    return RAGQueryResponse(
        answer=result["answer"],
        citations=citations,
        engine_values=result.get("engine_values"),
    )
