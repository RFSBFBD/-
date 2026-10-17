from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_profile
from app.db.session import get_db
from app.models.profile import Profile
from app.schemas.subject import (
    MemberCreate,
    MemberOut,
    SubjectCreate,
    SubjectListOut,
    SubjectOut,
    SubjectRename,
)
from app.services import subjects as subject_service
from app.services.subjects import SubjectAccess, SubjectError

router = APIRouter(prefix="/subjects", tags=["subjects"])


def _access_or_http(
    db: Session, subject_id: uuid.UUID, user: Profile
) -> SubjectAccess:
    try:
        return subject_service.get_subject_access(db, subject_id, user)
    except SubjectError as exc:
        raise _to_http(exc) from exc


def _to_http(exc: SubjectError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _to_out(access: SubjectAccess) -> SubjectOut:
    subject = access.subject
    return SubjectOut(
        id=subject.id,
        name=subject.name,
        role=access.role,
        archived_at=subject.archived_at,
        created_at=subject.created_at,
        updated_at=subject.updated_at,
    )


@router.post("", response_model=SubjectOut, status_code=201)
def create_subject(
    payload: SubjectCreate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> SubjectOut:
    try:
        subject = subject_service.create_subject(db, profile, payload.name)
    except SubjectError as exc:
        raise _to_http(exc) from exc
    return SubjectOut(
        id=subject.id,
        name=subject.name,
        role=subject_service.SUBJECT_ROLE_OWNER,
        archived_at=subject.archived_at,
        created_at=subject.created_at,
        updated_at=subject.updated_at,
    )


@router.get("", response_model=SubjectListOut)
def list_subjects(
    include_archived: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> SubjectListOut:
    items, total = subject_service.list_subjects(
        db, profile, include_archived=include_archived, limit=limit, offset=offset
    )
    return SubjectListOut(
        items=[_to_out(access) for access in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{subject_id}", response_model=SubjectOut)
def get_subject(
    subject_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> SubjectOut:
    return _to_out(_access_or_http(db, subject_id, profile))


@router.patch("/{subject_id}", response_model=SubjectOut)
def rename_subject(
    subject_id: uuid.UUID,
    payload: SubjectRename,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> SubjectOut:
    access = _access_or_http(db, subject_id, profile)
    try:
        subject_service.rename_subject(db, access, payload.name)
    except SubjectError as exc:
        raise _to_http(exc) from exc
    return _to_out(access)


@router.post("/{subject_id}/archive", response_model=SubjectOut)
def archive_subject(
    subject_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> SubjectOut:
    access = _access_or_http(db, subject_id, profile)
    try:
        subject_service.archive_subject(db, access)
    except SubjectError as exc:
        raise _to_http(exc) from exc
    return _to_out(access)


@router.post("/{subject_id}/unarchive", response_model=SubjectOut)
def unarchive_subject(
    subject_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> SubjectOut:
    access = _access_or_http(db, subject_id, profile)
    try:
        subject_service.unarchive_subject(db, access)
    except SubjectError as exc:
        raise _to_http(exc) from exc
    return _to_out(access)


@router.get("/{subject_id}/members", response_model=list[MemberOut])
def list_members(
    subject_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    access = _access_or_http(db, subject_id, profile)
    return [MemberOut.model_validate(m) for m in subject_service.list_members(db, access.subject.id)]


@router.post("/{subject_id}/members", response_model=MemberOut, status_code=201)
def add_member(
    subject_id: uuid.UUID,
    payload: MemberCreate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> MemberOut:
    access = _access_or_http(db, subject_id, profile)
    try:
        membership = subject_service.add_member(
            db, access, user_id=payload.user_id, role=payload.role
        )
    except SubjectError as exc:
        raise _to_http(exc) from exc
    return MemberOut.model_validate(membership)


@router.delete("/{subject_id}/members/{user_id}", status_code=204, response_class=Response)
def remove_member(
    subject_id: uuid.UUID,
    user_id: uuid.UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> Response:
    access = _access_or_http(db, subject_id, profile)
    try:
        subject_service.remove_member(db, access, user_id)
    except SubjectError as exc:
        raise _to_http(exc) from exc
    return Response(status_code=204)
