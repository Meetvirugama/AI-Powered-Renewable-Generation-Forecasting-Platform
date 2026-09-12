from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict

class Citation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    clause: str
    page: Optional[int] = None
    doc: str
    url: Optional[str] = ''

class RAGQueryRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    question: str
    plant_id: Optional[str] = None
    block_no: Optional[int] = None
    context: Optional[dict] = None

class RAGQueryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    answer: str
    citations: list[Citation]
    engine_values: Optional[dict] = None
