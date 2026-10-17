"""Audio transcription service.

Invariants:
- The material and subject membership are resolved server-side before any work.
- Only audio materials are transcribed; other types are rejected.
- Timestamps from the provider are validated (non-negative, monotonic, and
  ``end_ms >= start_ms``) before anything is stored.
- Re-transcribing a material replaces its prior segments in one transaction, so
  the operation is idempotent and never leaves partial data.
- Provider failures mark the material ``failed`` and re-raise a normalized
  provider error; no segments are persisted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.ai.base import AIProviderError, ParsedPage, TranscriptionProvider
from app.config import settings
from app.models.knowledge import UsageLog
from app.models.material import PROCESSING_FAILED, PROCESSING_PROCESSING, PROCESSING_READY
from app.models.profile import Profile
from app.models.transcript import TranscriptSegment
from app.services import audit
from app.services import materials as material_service
from app.storage.base import StorageError, StorageProvider

AUDIO_MATERIAL_TYPE = "audio"


class TranscriptionServiceError(Exception):
    status_code = 400


class NotAudioMaterial(TranscriptionServiceError):
    status_code = 422


class InvalidTranscript(TranscriptionServiceError):
    """Provider returned timestamps that violate the ordering contract."""

    status_code = 502


@dataclass(frozen=True)
class TranscriptionResult:
    material_id: uuid.UUID
    processing_status: str
    segment_count: int
    model: str
    detected_language: str | None


def _validate_segments(pages: list[ParsedPage]) -> None:
    previous_start = -1
    for page in pages:
        if page.start_ms is None or page.end_ms is None:
            raise InvalidTranscript("Transcription provider omitted timestamps.")
        if page.start_ms < 0 or page.end_ms < page.start_ms:
            raise InvalidTranscript("Transcription provider returned invalid timestamps.")
        if page.start_ms < previous_start:
            raise InvalidTranscript("Transcription segments are not time-ordered.")
        previous_start = page.start_ms


def _detected_language(pages: list[ParsedPage]) -> str | None:
    for page in pages:
        language = page.metadata.get("language")
        if isinstance(language, str) and language:
            return language
    return None


def transcribe_material(
    db: Session,
    storage: StorageProvider,
    provider: TranscriptionProvider,
    user: Profile,
    material_id: uuid.UUID,
    *,
    language: str | None = None,
) -> TranscriptionResult:
    material, stored = material_service.get_material(db, user, material_id)
    if material.material_type != AUDIO_MATERIAL_TYPE and not stored.mime_type.startswith("audio/"):
        raise NotAudioMaterial("Only audio materials can be transcribed.")

    material.processing_status = PROCESSING_PROCESSING
    audit.record_event(
        db,
        action="material.transcription_started",
        user_id=user.id,
        subject_id=material.subject_id,
        metadata={"material_id": str(material.id)},
    )

    try:
        data = storage.get_object(
            stored.storage_key, max_bytes=settings.max_upload_size_mb * 1024 * 1024
        )
        pages = provider.transcribe(
            data, filename=stored.original_filename, language=language
        )
        _validate_segments(pages)
    except (StorageError, AIProviderError, InvalidTranscript) as exc:
        material.processing_status = PROCESSING_FAILED
        audit.record_event(
            db,
            action="material.transcription_failed",
            user_id=user.id,
            subject_id=material.subject_id,
            metadata={"material_id": str(material.id), "reason": exc.__class__.__name__},
            commit=False,
        )
        db.commit()
        raise

    # Replace prior segments atomically so re-running is idempotent.
    db.execute(delete(TranscriptSegment).where(TranscriptSegment.material_id == material.id))
    for index, page in enumerate(pages):
        confidence = page.metadata.get("confidence")
        db.add(
            TranscriptSegment(
                material_id=material.id,
                subject_id=material.subject_id,
                segment_index=index,
                start_ms=page.start_ms or 0,
                end_ms=page.end_ms or 0,
                text=page.text,
                confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
                metadata_json=dict(page.metadata) or None,
            )
        )

    model_id = getattr(provider, "model_id", provider.__class__.__name__)
    db.add(
        UsageLog(
            user_id=user.id,
            subject_id=material.subject_id,
            provider="transcription",
            model_id=model_id,
            output_tokens=len(pages),
            status="success",
        )
    )
    material.processing_status = PROCESSING_READY
    audit.record_event(
        db,
        action="material.transcribed",
        user_id=user.id,
        subject_id=material.subject_id,
        metadata={"material_id": str(material.id), "segments": len(pages)},
        commit=False,
    )
    db.commit()
    return TranscriptionResult(
        material_id=material.id,
        processing_status=PROCESSING_READY,
        segment_count=len(pages),
        model=model_id,
        detected_language=_detected_language(pages),
    )


def list_segments(
    db: Session,
    user: Profile,
    material_id: uuid.UUID,
    *,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[TranscriptSegment], int]:
    from sqlalchemy import func, select

    material, _ = material_service.get_material(db, user, material_id)
    base = select(TranscriptSegment).where(TranscriptSegment.material_id == material.id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(
            base.order_by(TranscriptSegment.segment_index.asc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


__all__ = [
    "AUDIO_MATERIAL_TYPE",
    "InvalidTranscript",
    "NotAudioMaterial",
    "TranscriptionResult",
    "TranscriptionServiceError",
    "list_segments",
    "transcribe_material",
]
