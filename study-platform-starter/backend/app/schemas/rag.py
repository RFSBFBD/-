from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class IngestOut(BaseModel):
    material_id: uuid.UUID
    processing_status: str
    chunk_count: int
    embedded_count: int
    cached_count: int
    inserted_count: int


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class CitationOut(BaseModel):
    index: int
    material_id: uuid.UUID
    chunk_id: uuid.UUID
    title: str
    score: float
    snippet: str
    page_number: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None


class AskOut(BaseModel):
    answer: str
    citations: list[CitationOut]
    model: str
    used_context: bool


__all__ = ["AskIn", "AskOut", "CitationOut", "IngestOut"]
