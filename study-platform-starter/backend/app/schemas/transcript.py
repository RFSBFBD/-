from __future__ import annotations

import uuid

from pydantic import BaseModel


class TranscriptSegmentOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    segment_index: int
    start_ms: int
    end_ms: int
    text: str
    speaker_label: str | None = None
    confidence: float | None = None


class TranscriptOut(BaseModel):
    material_id: uuid.UUID
    segment_count: int
    total: int
    segments: list[TranscriptSegmentOut]


class TranscribeOut(BaseModel):
    material_id: uuid.UUID
    processing_status: str
    segment_count: int
    model: str
    detected_language: str | None = None


__all__ = ["TranscribeOut", "TranscriptOut", "TranscriptSegmentOut"]
