from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.base import AIProviderError, ProviderUnavailable, TranscriptionProvider
from app.ai.factory import get_transcription_provider
from app.auth.dependencies import get_current_profile
from app.db.session import get_db
from app.models.profile import Profile
from app.schemas.transcript import TranscribeOut, TranscriptOut, TranscriptSegmentOut
from app.services import materials as material_service
from app.services import transcription as transcription_service
from app.services.materials import MaterialError
from app.services.subjects import SubjectError
from app.storage import get_storage
from app.storage.base import StorageProvider

router = APIRouter(tags=["transcription"])


def get_transcription_provider_dep() -> TranscriptionProvider:
    try:
        return get_transcription_provider()
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _ensure_material_in_subject(
    db: Session, profile: Profile, subject_id: uuid.UUID, material_id: uuid.UUID
) -> None:
    try:
        material, _ = material_service.get_material(db, profile, material_id)
    except (MaterialError, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if material.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Material not found.")


@router.post(
    "/subjects/{subject_id}/materials/{material_id}/transcribe",
    response_model=TranscribeOut,
)
def transcribe_material(
    subject_id: uuid.UUID,
    material_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
    storage: StorageProvider = Depends(get_storage),
    provider: TranscriptionProvider = Depends(get_transcription_provider_dep),
) -> TranscribeOut:
    _ensure_material_in_subject(db, profile, subject_id, material_id)
    try:
        result = transcription_service.transcribe_material(
            db, storage, provider, profile, material_id
        )
    except (MaterialError, SubjectError, transcription_service.TranscriptionServiceError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TranscribeOut(
        material_id=result.material_id,
        processing_status=result.processing_status,
        segment_count=result.segment_count,
        model=result.model,
        detected_language=result.detected_language,
    )


@router.get(
    "/subjects/{subject_id}/materials/{material_id}/transcript",
    response_model=TranscriptOut,
)
def read_transcript(
    subject_id: uuid.UUID,
    material_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> TranscriptOut:
    _ensure_material_in_subject(db, profile, subject_id, material_id)
    try:
        segments, total = transcription_service.list_segments(db, profile, material_id)
    except (MaterialError, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return TranscriptOut(
        material_id=material_id,
        segment_count=len(segments),
        total=total,
        segments=[
            TranscriptSegmentOut(
                id=segment.id,
                material_id=segment.material_id,
                segment_index=segment.segment_index,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text,
                speaker_label=segment.speaker_label,
                confidence=segment.confidence,
            )
            for segment in segments
        ],
    )
