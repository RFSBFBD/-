from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.db.session import get_db
from app.models.profile import Profile
from app.schemas.study_session import StudyLimitsOut, StudyLimitsUpdate
from app.services import app_config
from app.services.app_config import ConfigValueError

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
def admin_ping(admin: Profile = Depends(require_admin)) -> dict[str, str]:
    """Admin-only probe used to verify server-side role enforcement."""
    return {"status": "ok", "role": admin.role}


@router.get("/study-session-settings", response_model=StudyLimitsOut)
def read_study_session_settings(
    _: Profile = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StudyLimitsOut:
    minimum, maximum = app_config.get_study_session_limits(db)
    return StudyLimitsOut(min_minutes=minimum, max_minutes=maximum)


@router.put("/study-session-settings", response_model=StudyLimitsOut)
def update_study_session_settings(
    payload: StudyLimitsUpdate,
    _: Profile = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StudyLimitsOut:
    try:
        minimum, maximum = app_config.set_study_session_limits(
            db, min_minutes=payload.min_minutes, max_minutes=payload.max_minutes
        )
    except ConfigValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StudyLimitsOut(min_minutes=minimum, max_minutes=maximum)
