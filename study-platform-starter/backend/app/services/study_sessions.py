"""Server-authoritative study session engine.

Rules enforced server-side:
- One active session per user (partial unique index + pre-check).
- The chosen duration must be within admin-configured bounds.
- The subject must be one the caller can access; archived subjects are rejected.
- Timing uses server time only; client-supplied timestamps are ignored.
- Expiry is computed against server time and finalized safely on read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clock import as_utc, utcnow
from app.models.profile import Profile
from app.models.study_session import (
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_CANCELLED,
    SESSION_STATUS_COMPLETED,
    StudySession,
)
from app.services import app_config, audit
from app.services import subjects as subject_service
from app.services.subjects import SubjectArchived


class StudySessionError(Exception):
    status_code = 400


class SessionNotFound(StudySessionError):
    status_code = 404


class InvalidDuration(StudySessionError):
    status_code = 422


class SessionAlreadyActive(StudySessionError):
    status_code = 409

    def __init__(self, session: StudySession) -> None:
        super().__init__("An active study session already exists.")
        self.session = session


@dataclass(frozen=True)
class SessionView:
    session: StudySession
    remaining_seconds: int


def _remaining(session: StudySession, now) -> int:
    return max(0, int((as_utc(session.ends_at) - now).total_seconds()))


def remaining_seconds(session: StudySession) -> int:
    return _remaining(session, utcnow())


def get_active_session(db: Session, user: Profile) -> StudySession | None:
    """Return the user's active session, finalizing it if it has expired."""
    session = db.execute(
        select(StudySession).where(
            StudySession.user_id == user.id,
            StudySession.status == SESSION_STATUS_ACTIVE,
        )
    ).scalar_one_or_none()

    if session is None:
        return None

    if as_utc(session.ends_at) <= utcnow():
        session.status = SESSION_STATUS_COMPLETED
        db.commit()
        db.refresh(session)
        audit.record_event(
            db,
            action="study_session.expired",
            user_id=user.id,
            subject_id=session.subject_id,
            metadata={"session_id": str(session.id)},
        )
        return None

    return session


def view_active_session(db: Session, user: Profile) -> SessionView | None:
    session = get_active_session(db, user)
    if session is None:
        return None
    return SessionView(session=session, remaining_seconds=_remaining(session, utcnow()))


def start_session(
    db: Session, user: Profile, *, subject_id: uuid.UUID, duration_minutes: int
) -> tuple[StudySession, bool]:
    """Start a session. Returns (session, created). Idempotent for the same subject."""
    min_minutes, max_minutes = app_config.get_study_session_limits(db)
    if duration_minutes < min_minutes or duration_minutes > max_minutes:
        raise InvalidDuration(
            f"Duration must be between {min_minutes} and {max_minutes} minutes."
        )

    access = subject_service.get_subject_access(db, subject_id, user)

    if access.subject.archived_at is not None:
        raise SubjectArchived("Archived subjects cannot start a study session.")

    existing = get_active_session(db, user)
    if existing is not None:
        if existing.subject_id == subject_id:
            return existing, False
        raise SessionAlreadyActive(existing)

    now = utcnow()
    session = StudySession(
        user_id=user.id,
        subject_id=subject_id,
        started_at=now,
        ends_at=now + timedelta(minutes=duration_minutes),
        status=SESSION_STATUS_ACTIVE,
    )
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = get_active_session(db, user)
        if concurrent is not None:
            raise SessionAlreadyActive(concurrent) from None
        raise
    db.refresh(session)

    audit.record_event(
        db,
        action="study_session.started",
        user_id=user.id,
        subject_id=subject_id,
        metadata={"session_id": str(session.id), "duration_minutes": duration_minutes},
    )
    return session, True


def end_session(
    db: Session, user: Profile, session_id: uuid.UUID, *, cancelled: bool = False
) -> StudySession:
    session = db.get(StudySession, session_id)
    if session is None or session.user_id != user.id:
        raise SessionNotFound("Study session not found.")
    if session.status == SESSION_STATUS_ACTIVE:
        session.status = SESSION_STATUS_CANCELLED if cancelled else SESSION_STATUS_COMPLETED
        db.commit()
        db.refresh(session)
        audit.record_event(
            db,
            action="study_session.cancelled" if cancelled else "study_session.completed",
            user_id=user.id,
            subject_id=session.subject_id,
            metadata={"session_id": str(session.id)},
        )
    return session


__all__ = [
    "InvalidDuration",
    "SessionAlreadyActive",
    "SessionNotFound",
    "SessionView",
    "StudySessionError",
    "end_session",
    "get_active_session",
    "remaining_seconds",
    "start_session",
    "view_active_session",
]
