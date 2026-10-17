from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_profile
from app.db.session import get_db
from app.models.material import DuplicateReview, Material, StoredFile
from app.models.profile import Profile
from app.schemas.material import (
    DownloadUrlOut,
    DuplicateReviewListOut,
    DuplicateReviewOut,
    MaterialListOut,
    MaterialOut,
    MaterialUploadOut,
    ResolveReviewIn,
)
from app.services import materials as material_service
from app.services.materials import MaterialError
from app.services.rate_limit import RateLimitExceeded, get_upload_limiter
from app.services.subjects import SubjectError
from app.storage import get_storage
from app.storage.base import StorageProvider

router = APIRouter(tags=["materials"])


def _to_material_out(material: Material, stored: StoredFile) -> MaterialOut:
    return MaterialOut(
        id=material.id,
        subject_id=material.subject_id,
        title=material.title,
        material_type=material.material_type,
        processing_status=material.processing_status,
        duplicate_status=material.duplicate_status,
        uploader_id=material.uploader_id,
        original_filename=stored.original_filename,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        created_at=material.created_at,
    )


def _to_review_out(review: DuplicateReview) -> DuplicateReviewOut:
    return DuplicateReviewOut(
        id=review.id,
        subject_id=review.subject_id,
        candidate_material_id=review.candidate_material_id,
        matched_material_id=review.matched_material_id,
        similarity_score=review.similarity_score,
        status=review.status,
        reviewer_id=review.reviewer_id,
        reviewed_at=review.reviewed_at,
        created_at=review.created_at,
    )


@router.get("/subjects/{subject_id}/materials", response_model=MaterialListOut)
def list_materials(
    subject_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> MaterialListOut:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    try:
        rows, total = material_service.list_materials(
            db, profile, subject_id=subject_id, limit=limit, offset=offset
        )
    except SubjectError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return MaterialListOut(
        items=[_to_material_out(m, s) for m, s in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/subjects/{subject_id}/materials", response_model=MaterialUploadOut)
async def upload_material(
    subject_id: uuid.UUID,
    response: Response,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
    storage: StorageProvider = Depends(get_storage),
):
    limiter = get_upload_limiter()
    try:
        limiter.check(f"upload:{profile.id}")
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    data = await file.read()
    try:
        outcome = material_service.create_material(
            db,
            storage,
            profile,
            subject_id=subject_id,
            filename=file.filename or "upload",
            declared_content_type=file.content_type,
            data=data,
            title=title,
        )
    except (MaterialError, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    response.status_code = 201 if outcome.created else 200
    return MaterialUploadOut(
        material=_to_material_out(outcome.material, outcome.stored_file),
        created=outcome.created,
        duplicate=outcome.duplicate,
        duplicate_material_id=outcome.duplicate_material_id,
    )


@router.get("/materials/{material_id}", response_model=MaterialOut)
def read_material(
    material_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> MaterialOut:
    try:
        material, stored = material_service.get_material(db, profile, material_id)
    except (MaterialError, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return _to_material_out(material, stored)


@router.get("/materials/{material_id}/download", response_model=DownloadUrlOut)
def download_material(
    material_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
    storage: StorageProvider = Depends(get_storage),
) -> DownloadUrlOut:
    try:
        url, expires_in = material_service.create_download_url(
            db, storage, profile, material_id
        )
    except (MaterialError, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return DownloadUrlOut(url=url, expires_in=expires_in)


@router.delete("/materials/{material_id}", status_code=204, response_class=Response)
def delete_material(
    material_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> Response:
    try:
        material_service.delete_material(db, profile, material_id)
    except (MaterialError, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/subjects/{subject_id}/duplicate-reviews", response_model=DuplicateReviewListOut)
def list_duplicate_reviews(
    subject_id: uuid.UUID,
    status: str = "pending",
    limit: int = 20,
    offset: int = 0,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> DuplicateReviewListOut:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    try:
        rows, total = material_service.list_reviews(
            db, profile, subject_id=subject_id, status=status, limit=limit, offset=offset
        )
    except (MaterialError, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return DuplicateReviewListOut(
        items=[_to_review_out(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/duplicate-reviews/{review_id}/resolve", response_model=DuplicateReviewOut)
def resolve_duplicate_review(
    review_id: uuid.UUID,
    payload: ResolveReviewIn,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> DuplicateReviewOut:
    try:
        review = material_service.resolve_review(
            db, profile, review_id, decision=payload.decision
        )
    except (MaterialError, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return _to_review_out(review)
