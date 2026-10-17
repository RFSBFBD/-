from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.base import AIProviderError, ChatModel
from app.auth.dependencies import get_current_profile
from app.db.session import get_db
from app.models.artifact import ArtifactFeedback, GeneratedArtifact
from app.models.profile import Profile
from app.schemas.artifact import (
    ArtifactFeedbackIn,
    ArtifactGenerateIn,
    ArtifactListOut,
    ArtifactOut,
    FeedbackOut,
)
from app.services import artifacts as artifact_service
from app.services import materials as material_service
from app.services import subjects as subject_service
from app.services.materials import MaterialError
from app.services.subjects import SubjectError
from app.routers.rag import get_chat_model_dep

router = APIRouter(tags=["artifacts"])


def _to_out(artifact: GeneratedArtifact, *, cached: bool = False) -> ArtifactOut:
    return ArtifactOut(
        id=artifact.id,
        subject_id=artifact.subject_id,
        material_id=artifact.material_id,
        artifact_type=artifact.artifact_type,
        model_id=artifact.model_id,
        prompt_version=artifact.prompt_version,
        input_hash=artifact.input_hash,
        payload=artifact.payload_json,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
        cached=cached,
    )


def _to_feedback_out(feedback: ArtifactFeedback) -> FeedbackOut:
    return FeedbackOut(
        id=feedback.id,
        artifact_id=feedback.artifact_id,
        user_id=feedback.user_id,
        rating=feedback.rating,
        comment=feedback.comment,
        created_at=feedback.created_at,
    )


@router.post("/subjects/{subject_id}/artifacts", response_model=ArtifactOut)
def create_artifact(
    subject_id: uuid.UUID,
    payload: ArtifactGenerateIn,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
    chat_model: ChatModel = Depends(get_chat_model_dep),
) -> ArtifactOut:
    try:
        result = artifact_service.generate_artifact(
            db,
            chat_model,
            profile,
            subject_id=subject_id,
            artifact_type=payload.artifact_type,
            material_ids=payload.material_ids,
            topic=payload.topic,
            language=payload.language,
            force=payload.force,
        )
    except (MaterialError, SubjectError, artifact_service.ArtifactError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _to_out(result.artifact, cached=result.cached)


@router.get("/subjects/{subject_id}/artifacts", response_model=ArtifactListOut)
def list_artifacts(
    subject_id: uuid.UUID,
    artifact_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> ArtifactListOut:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    try:
        rows, total = artifact_service.list_artifacts(
            db,
            profile,
            subject_id=subject_id,
            artifact_type=artifact_type,
            limit=limit,
            offset=offset,
        )
    except (MaterialError, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ArtifactListOut(
        items=[_to_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
def read_artifact(
    artifact_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> ArtifactOut:
    try:
        artifact = artifact_service.get_artifact(db, profile, artifact_id)
    except (MaterialError, SubjectError, artifact_service.ArtifactError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return _to_out(artifact)


@router.post("/artifacts/{artifact_id}/regenerate", response_model=ArtifactOut)
def regenerate_artifact(
    artifact_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
    chat_model: ChatModel = Depends(get_chat_model_dep),
) -> ArtifactOut:
    try:
        existing = artifact_service.get_artifact(db, profile, artifact_id)
        payload = existing.payload_json or {}
        material_ids = payload.get("source_material_ids") or []
        if not material_ids:
            raise artifact_service.ArtifactValidationError(
                "This artifact cannot be regenerated because its sources are unknown."
            )
        result = artifact_service.generate_artifact(
            db,
            chat_model,
            profile,
            subject_id=existing.subject_id,
            artifact_type=existing.artifact_type,
            material_ids=[uuid.UUID(value) for value in material_ids],
            topic=payload.get("topic"),
            force=True,
        )
    except (MaterialError, SubjectError, artifact_service.ArtifactError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _to_out(result.artifact, cached=False)


@router.post("/artifacts/{artifact_id}/feedback", response_model=FeedbackOut)
def submit_feedback(
    artifact_id: uuid.UUID,
    payload: ArtifactFeedbackIn,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> FeedbackOut:
    try:
        feedback = artifact_service.add_feedback(
            db, profile, artifact_id, rating=payload.rating, comment=payload.comment
        )
    except (MaterialError, SubjectError, artifact_service.ArtifactError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return _to_feedback_out(feedback)
