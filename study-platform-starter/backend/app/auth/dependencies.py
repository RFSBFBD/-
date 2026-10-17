"""Authorization dependencies.

All protected routes depend on a verified identity. The local profile (and its
role) is resolved server-side; roles are never taken from the request body.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.supabase import AuthenticationError, SupabaseTokenVerifier, VerifiedIdentity
from app.config import settings
from app.db.session import get_db
from app.models.profile import ROLE_ADMIN, Profile
from app.services.profiles import get_or_create_profile


@lru_cache(maxsize=1)
def get_verifier() -> SupabaseTokenVerifier:
    return SupabaseTokenVerifier(
        issuer=settings.supabase_issuer_url,
        jwks_url=settings.supabase_jwks_url_resolved,
        audience=settings.supabase_audience,
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise _unauthorized("Missing authorization header.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized("Authorization header must use the Bearer scheme.")
    return token.strip()


def get_identity(
    token: str = Depends(get_bearer_token),
    verifier: SupabaseTokenVerifier = Depends(get_verifier),
) -> VerifiedIdentity:
    if not verifier.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication provider is not configured.",
        )
    try:
        return verifier.verify(token)
    except AuthenticationError as exc:
        raise _unauthorized(str(exc)) from exc


def get_current_profile(
    identity: VerifiedIdentity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> Profile:
    return get_or_create_profile(db, identity)


def require_admin(profile: Profile = Depends(get_current_profile)) -> Profile:
    if profile.role != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges are required.",
        )
    return profile


__all__ = [
    "get_bearer_token",
    "get_current_profile",
    "get_identity",
    "get_verifier",
    "require_admin",
]
