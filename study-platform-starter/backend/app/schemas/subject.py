from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SubjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class SubjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: str
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SubjectListOut(BaseModel):
    items: list[SubjectOut]
    total: int
    limit: int
    offset: int


class MemberCreate(BaseModel):
    user_id: uuid.UUID
    role: str = Field(default="member", max_length=32)


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    role: str
    joined_at: datetime


__all__ = [
    "MemberCreate",
    "MemberOut",
    "SubjectCreate",
    "SubjectListOut",
    "SubjectOut",
    "SubjectRename",
]
