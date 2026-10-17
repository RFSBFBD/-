from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MaterialOut(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    title: str
    material_type: str
    processing_status: str
    duplicate_status: str
    uploader_id: uuid.UUID | None
    original_filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime


class MaterialListOut(BaseModel):
    items: list[MaterialOut]
    total: int
    limit: int
    offset: int


class MaterialUploadOut(BaseModel):
    material: MaterialOut
    created: bool
    duplicate: str
    duplicate_material_id: uuid.UUID | None = None


class DownloadUrlOut(BaseModel):
    url: str
    expires_in: int


class DuplicateReviewOut(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    candidate_material_id: uuid.UUID
    matched_material_id: uuid.UUID
    similarity_score: float
    status: str
    reviewer_id: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class DuplicateReviewListOut(BaseModel):
    items: list[DuplicateReviewOut]
    total: int
    limit: int
    offset: int


class ResolveReviewIn(BaseModel):
    decision: str = Field(pattern="^(confirm|dismiss)$")


__all__ = [
    "DownloadUrlOut",
    "DuplicateReviewListOut",
    "DuplicateReviewOut",
    "MaterialListOut",
    "MaterialOut",
    "MaterialUploadOut",
    "ResolveReviewIn",
]
