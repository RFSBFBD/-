from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class StudySessionStart(BaseModel):
    subject_id: uuid.UUID
    duration_minutes: int = Field(ge=1, le=600)


class StudySessionOut(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    status: str
    started_at: datetime
    ends_at: datetime
    remaining_seconds: int
    server_now: datetime


class ActiveSessionOut(BaseModel):
    active_session: StudySessionOut | None
    server_now: datetime


class StudyLimitsOut(BaseModel):
    min_minutes: int
    max_minutes: int


class StudyLimitsUpdate(BaseModel):
    min_minutes: int = Field(ge=1, le=600)
    max_minutes: int = Field(ge=1, le=600)


__all__ = [
    "ActiveSessionOut",
    "StudyLimitsOut",
    "StudyLimitsUpdate",
    "StudySessionOut",
    "StudySessionStart",
]
