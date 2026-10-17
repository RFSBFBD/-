"""Profile sync service.

Creates/updates the local ``profiles`` row from a verified identity. The role is
always assigned by the server; client-supplied values are never consulted.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.supabase import VerifiedIdentity
from app.models.profile import ROLE_STUDENT, Profile


def get_profile_by_auth_id(db: Session, auth_user_id: str) -> Profile | None:
    return db.execute(
        select(Profile).where(Profile.auth_user_id == auth_user_id)
    ).scalar_one_or_none()


def get_or_create_profile(db: Session, identity: VerifiedIdentity) -> Profile:
    existing = get_profile_by_auth_id(db, identity.user_id)
    if existing is not None:
        name = _display_name(identity)
        if name and not existing.display_name:
            existing.display_name = name
            db.commit()
            db.refresh(existing)
        return existing

    profile = Profile(
        auth_user_id=identity.user_id,
        display_name=_display_name(identity),
        role=ROLE_STUDENT,
    )
    db.add(profile)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent first-login race: another request created the row.
        db.rollback()
        created = get_profile_by_auth_id(db, identity.user_id)
        if created is None:
            raise
        return created
    db.refresh(profile)
    return profile


def _display_name(identity: VerifiedIdentity) -> str | None:
    metadata = identity.claims.get("user_metadata")
    candidates = [
        identity.claims.get("name"),
        identity.claims.get("full_name"),
        metadata.get("full_name") if isinstance(metadata, dict) else None,
        metadata.get("name") if isinstance(metadata, dict) else None,
        identity.email,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


__all__ = ["get_or_create_profile", "get_profile_by_auth_id"]
