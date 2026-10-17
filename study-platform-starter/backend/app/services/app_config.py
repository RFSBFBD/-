"""Admin-editable application configuration (key/value)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.app_config import AppConfig

STUDY_SESSION_MIN_KEY = "study_session.min_minutes"
STUDY_SESSION_MAX_KEY = "study_session.max_minutes"

DEFAULT_MIN_MINUTES = 5
DEFAULT_MAX_MINUTES = 180
HARD_MAX_MINUTES = 600


class ConfigValueError(ValueError):
    pass


def get_value(db: Session, key: str) -> str | None:
    row = db.get(AppConfig, key)
    return row.value if row else None


def set_value(db: Session, key: str, value: str) -> None:
    row = db.get(AppConfig, key)
    if row is None:
        db.add(AppConfig(key=key, value=value))
    else:
        row.value = value
    db.commit()


def get_study_session_minutes(db: Session) -> int:
    return _as_int(get_value(db, STUDY_SESSION_MIN_KEY), DEFAULT_MIN_MINUTES)


def get_study_session_max_minutes(db: Session) -> int:
    return _as_int(get_value(db, STUDY_SESSION_MAX_KEY), DEFAULT_MAX_MINUTES)


def get_study_session_limits(db: Session) -> tuple[int, int]:
    return get_study_session_minutes(db), get_study_session_max_minutes(db)


def set_study_session_limits(db: Session, *, min_minutes: int, max_minutes: int) -> tuple[int, int]:
    if min_minutes < 1:
        raise ConfigValueError("Minimum duration must be at least 1 minute.")
    if max_minutes > HARD_MAX_MINUTES:
        raise ConfigValueError(f"Maximum duration must not exceed {HARD_MAX_MINUTES} minutes.")
    if min_minutes > max_minutes:
        raise ConfigValueError("Minimum duration must not exceed maximum duration.")
    set_value(db, STUDY_SESSION_MIN_KEY, str(min_minutes))
    set_value(db, STUDY_SESSION_MAX_KEY, str(max_minutes))
    return min_minutes, max_minutes


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "ConfigValueError",
    "DEFAULT_MAX_MINUTES",
    "DEFAULT_MIN_MINUTES",
    "HARD_MAX_MINUTES",
    "get_study_session_limits",
    "get_study_session_max_minutes",
    "get_study_session_minutes",
    "set_study_session_limits",
]
