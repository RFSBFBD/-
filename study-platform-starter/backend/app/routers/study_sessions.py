from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_profile
from app.clock import utcnow
from app.db.session import get_db
from app.logging_config import get_request_id
from app.models.profile import Profile
from app.models.study_session import StudySession
from app.schemas.study_session import (
    ActiveSessionOut,
    StudyLimitsOut,
    StudySessionOut,
    StudySessionStart,
)
from app.services import app_config
from app.services import study_sessions as session_service
from app.services.study_sessions import (
    InvalidDuration,
    SessionAlreadyActive,
    SessionNotFound,
    StudySessionError,
)
from app.services.subjects import SubjectError

router = APIRouter(prefix="/study-sessions", tags=["study-sessions"])


def _to_out(session: StudySession) -> StudySessionOut:
    return StudySessionOut(
        id=session.id,
        subject_id=session.subject_id,
        status=session.status,
        started_at=session.started_at,
        ends_at=session.ends_at,
        remaining_seconds=session_service.remaining_seconds(session),
        server_now=utcnow(),
    )


def _session_active_response(exc: SessionAlreadyActive) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "type": "session_already_active",
                "message": "An active study session already exists.",
                "request_id": get_request_id(),
                "active_session": _to_out(exc.session).model_dump(mode="json"),
            }
        },
    )


@router.get("/limits", response_model=StudyLimitsOut)
def read_limits(
    _: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> StudyLimitsOut:
    minimum, maximum = app_config.get_study_session_limits(db)
    return StudyLimitsOut(min_minutes=minimum, max_minutes=maximum)


@router.get("/active", response_model=ActiveSessionOut)
def read_active(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> ActiveSessionOut:
    session = session_service.get_active_session(db, profile)
    return ActiveSessionOut(
        active_session=_to_out(session) if session else None,
        server_now=utcnow(),
    )


@router.post("", response_model=StudySessionOut)
def start_session(
    payload: StudySessionStart,
    response: Response,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    try:
        session, created = session_service.start_session(
            db, profile, subject_id=payload.subject_id, duration_minutes=payload.duration_minutes
        )
    except SessionAlreadyActive as exc:
        return _session_active_response(exc)
    except (InvalidDuration, SubjectError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    response.status_code = 201 if created else 200
    return _to_out(session)


@router.post("/{session_id}/end", response_model=StudySessionOut)
def end_session(
    session_id: uuid.UUID,
    cancel: bool = False,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> StudySessionOut:
    try:
        session = session_service.end_session(db, profile, session_id, cancelled=cancel)
    except (SessionNotFound, StudySessionError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return _to_out(session)
