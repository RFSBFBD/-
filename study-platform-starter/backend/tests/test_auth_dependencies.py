from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.supabase import AuthenticationError, SupabaseTokenVerifier, VerifiedIdentity
from app.auth.dependencies import get_identity, get_verifier
from app.main import app
from app.models.profile import ROLE_ADMIN, ROLE_STUDENT, Profile


def _identity(user_id: str = "user_abc", **claim_overrides) -> VerifiedIdentity:
    claims = {"name": "Student One"}
    claims.update(claim_overrides)
    return VerifiedIdentity(user_id=user_id, claims=claims)


def _override_identity(identity: VerifiedIdentity) -> None:
    app.dependency_overrides[get_identity] = lambda: identity


def test_missing_token_is_unauthorized(client: TestClient):
    response = client.get("/me")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_malformed_authorization_header_is_unauthorized(client: TestClient):
    response = client.get("/me", headers={"Authorization": "Token abc"})
    assert response.status_code == 401


def test_invalid_token_is_unauthorized(client: TestClient):
    def broken_resolver(_token: str):
        raise AuthenticationError("bad token")

    app.dependency_overrides[get_verifier] = lambda: SupabaseTokenVerifier(
        issuer="https://supabase.example.com",
        jwks_url="https://supabase.example.com/jwks",
        key_resolver=broken_resolver,
    )
    try:
        response = client.get("/me", headers={"Authorization": "Bearer garbage"})
    finally:
        app.dependency_overrides.pop(get_verifier, None)
    assert response.status_code == 401


def test_unconfigured_provider_returns_service_unavailable(client: TestClient):
    app.dependency_overrides[get_verifier] = lambda: SupabaseTokenVerifier(
        issuer="", jwks_url="", audience="authenticated"
    )
    try:
        response = client.get("/me", headers={"Authorization": "Bearer something"})
    finally:
        app.dependency_overrides.pop(get_verifier, None)
    assert response.status_code == 503


def test_first_login_creates_student_profile(client: TestClient, db_session: Session):
    _override_identity(_identity())
    try:
        response = client.get("/me")
    finally:
        app.dependency_overrides.pop(get_identity, None)

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == ROLE_STUDENT
    assert body["display_name"] == "Student One"

    count = db_session.execute(select(func.count()).select_from(Profile)).scalar_one()
    assert count == 1


def test_profile_sync_is_idempotent(client: TestClient, db_session: Session):
    _override_identity(_identity())
    try:
        first = client.get("/me").json()
        second = client.get("/me").json()
    finally:
        app.dependency_overrides.pop(get_identity, None)

    assert first["id"] == second["id"]
    count = db_session.execute(select(func.count()).select_from(Profile)).scalar_one()
    assert count == 1


def test_role_cannot_be_escalated_by_claims(client: TestClient):
    # A token claiming an admin role must NOT influence the server-assigned role.
    _override_identity(_identity(role="admin", is_admin=True))
    try:
        response = client.get("/me")
    finally:
        app.dependency_overrides.pop(get_identity, None)
    assert response.status_code == 200
    assert response.json()["role"] == ROLE_STUDENT


def test_student_cannot_access_admin_route(client: TestClient):
    _override_identity(_identity())
    try:
        response = client.get("/admin/ping")
    finally:
        app.dependency_overrides.pop(get_identity, None)
    assert response.status_code == 403


def test_admin_can_access_admin_route(client: TestClient, db_session: Session):
    _override_identity(_identity())
    try:
        client.get("/me")  # create the profile first
    finally:
        app.dependency_overrides.pop(get_identity, None)

    profile = db_session.execute(select(Profile)).scalar_one()
    profile.role = ROLE_ADMIN
    db_session.commit()

    _override_identity(_identity())
    try:
        response = client.get("/admin/ping")
    finally:
        app.dependency_overrides.pop(get_identity, None)
    assert response.status_code == 200
    assert response.json()["role"] == ROLE_ADMIN
