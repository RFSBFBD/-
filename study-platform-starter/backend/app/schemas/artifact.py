from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ArtifactGenerateIn(BaseModel):
    artifact_type: str = Field(
        pattern="^(notes|quiz|quiz_explanation|revision_cards|mind_map|code_descriptions|concept_alignment)$"
    )
    material_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    topic: str | None = Field(default=None, max_length=500)
    language: str | None = Field(default=None, max_length=20)
    force: bool = False


class ArtifactFeedbackIn(BaseModel):
    rating: str = Field(pattern="^(up|down)$")
    comment: str | None = Field(default=None, max_length=1000)


class ArtifactOut(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    material_id: uuid.UUID | None
    artifact_type: str
    model_id: str
    prompt_version: str
    input_hash: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    cached: bool = False


class ArtifactListOut(BaseModel):
    items: list[ArtifactOut]
    total: int
    limit: int
    offset: int


class FeedbackOut(BaseModel):
    id: uuid.UUID
    artifact_id: uuid.UUID
    user_id: uuid.UUID | None
    rating: str
    comment: str | None
    created_at: datetime


__all__ = [
    "ArtifactFeedbackIn",
    "ArtifactGenerateIn",
    "ArtifactListOut",
    "ArtifactOut",
    "FeedbackOut",
]
