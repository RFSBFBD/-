from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_profile
from app.models.profile import Profile
from app.schemas.profile import ProfileOut

router = APIRouter(tags=["account"])


@router.get("/me", response_model=ProfileOut)
def read_me(profile: Profile = Depends(get_current_profile)) -> Profile:
    """Return the authenticated user's local profile."""
    return profile
