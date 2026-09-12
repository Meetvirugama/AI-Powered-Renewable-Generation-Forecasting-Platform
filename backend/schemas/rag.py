from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from typing import Optional


class Citation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    clause: str
    page: Optional[int] = None
    doc: str
    url: Optional[str] = ''
    section: Optional[str] = None
    snippet: Optional[str] = None


class RAGQueryRequest(BaseModel):
    # populate_by_name lets the field be set by its own name as well as by the
    # aliases declared below.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    question: str = Field(min_length=3, max_length=1000)
    plant_id: Optional[str] = None
    block_no: Optional[int] = Field(default=None, ge=1, le=288)
    date: Optional[str] = None
    # Selects which regulation set the copilot may cite. Without it the answer
    # can cite the 2026 amendment while the UI slider is showing 2024.
    rule_year: Optional[int] = Field(default=None, ge=2024, le=2031)
    # DSM engine output for the block in question. Authoritative: the copilot
    # explains these numbers, it never recomputes or invents them.
    #
    # `engine_context` is accepted as a synonym because the Member 4 execution
    # plan drafted the field under that name before this schema existed, and
    # both docs are in the repo. Accepting both costs one line and removes a
    # whole class of integration bug; `context` stays canonical.
    context: Optional[dict] = Field(
        default=None,
        validation_alias=AliasChoices("context", "engine_context"),
    )


class RAGMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    llm_model: Optional[str] = None
    cached: bool = False
    latency_ms: Optional[int] = None
    retrieved_chunks: int = 0
    # pass | numbers_stripped | fallback_template
    # numbers_stripped means the copilot produced a figure the DSM engine did
    # not, and it was removed before the answer left the server.
    guardrail: str = 'pass'


class RAGQueryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    answer: str
    citations: list[Citation]
    engine_values: Optional[dict] = None
    meta: RAGMeta = RAGMeta()
