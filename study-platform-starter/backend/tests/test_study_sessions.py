from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.supabase import VerifiedIdentity
from app.auth.dependencies import get_identity
from app.main import app
from app.models.audit import AuditEvent
from app.models.profile import ROLE_ADMIN, Profile
from app.services import study_sessions as session_service


def as_user(user_id: str, name: str = "User") -> None:
    app.dependency_overrides[get_identity] = lambda: VerifiedIdentity(
    user_id=user_id, claims={"name": name}
)


def clear_user() -> None:
    app.dependency_overrides.pop(get_identity, None)


def make_subject(client: TestClient, name: str) -> str:
    return client.post("/subjects", json={"name": name}).json()["id"]


def make_second_subject(client: TestClient, name: str) -> str:
    return client.post("/subjects", json={"name": name}).json()["id"]


def test_default_limits(client: TestClient):
    as_user("user_a")
    try:
        limits = client.get("/study-sessions/limits").json()
    finally:
        clear_user()
    assert limits == {"min_minutes": 5, "max_minutes": 180}


def test_start_session_within_bounds(client: TestClient):
    as_user("user_a")
    try:
        subject_id = make_subject(client, "Math")
        response = client.post(
            "/study-sessions", json={"subject_id": subject_id, "duration_minutes": 30}
        )
    finally:
        clear_user()
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active"
    assert body["subject_id"] == subject_id
    assert 0 < body["remaining_seconds"] <= 30 * 60


def test_duration_below_minimum_is_rejected(client: TestClient):
    as_user("user_a")
    try:
        subject_id = make_subject(client, "Math")
        response = client.post(
            "/study-sessions", json={"subject_id": subject_id, "duration_minutes": 1}
        )
    finally:
        clear_user()
    assert response.status_code == 422


def test_duration_above_maximum_is_rejected(client: TestClient):
    as_user("user_a")
    try:
        subject_id = make_subject(client, "Math")
        response = client.post(
            "/study-sessions", json={"subject_id": subject_id, "duration_minutes": 181}
        )
    finally:
        clear_user()
    assert response.status_code == 422


def test_cannot_start_session_for_inaccessible_subject(client: TestClient):
    as_user("user_a")
    try:
        subject_id = make_subject(client, "Private")
    finally:
        clear_user()
    as_user("user_b")
    try:
        response = client.post(
            "/study-sessions", json={"subject_id": subject_id, "duration_minutes": 30}
        )
    finally:
        clear_user()
    assert response.status_code == 404


def test_client_supplied_timestamps_are_ignored(client: TestClient):
    as_user("user_a")
    try:
        subject_id = make_subject(client, "Math")
        response = client.post(
            "/study-sessions",
            json={
                "subject_id": subject_id,
                "duration_minutes": 30,
                "started_at": "2000-01-01T00:00:00Z",
                "ends_at": "2000-01-01T00:00:01Z",
            },
        )
    finally:
        clear_user()
    body = response.json()
    started = dt.datetime.fromisoformat(body["started_at"].replace("Z", "+00:00"))
    assert started.year >= 2026


def test_second_different_subject_session_conflicts(client: TestClient):
    as_user("user_a")
    try:
        first = make_subject(client, "Math")
        second = make_second_subject(client, "Physics")
        client.post("/study-sessions", json={"subject_id": first, "duration_minutes": 30})
        response = client.post("/study-sessions", json={"subject_id": second, "duration_minutes": 30})
    finally:
        clear_user()
    assert response.status_code == 409
    payload = response.json()["error"]
    assert payload["type"] == "session_already_active"
    assert payload["active_session"]["subject_id"] == first


def test_same_subject_restart_is_idempotent(client: TestClient):
    as_user("user_a")
    try:
        subject_id = make_subject(client, "Math")
        first = client.post("/study-sessions", json={"subject_id": subject_id, "duration_minutes": 30})
        second = client.post("/study-sessions", json={"subject_id": subject_id, "duration_minutes": 30})
    finally:
        clear_user()
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_active_session_survives_reload_and_concurrent_tabs(client: TestClient):
    as_user("user_a")
    try:
        subject_id = make_subject(client, "Math")
        started = client.post("/study-sessions", json={"subject_id": subject_id, "duration_minutes": 30}).json()
        tab_one = client.get("/study-sessions/active").json()
        tab_two = client.get("/study-sessions/active").json()
    finally:
        clear_user()
    assert tab_one["active_session"]["id"] == started["id"]
    assert tab_two["active_session"]["id"] == started["id"]


def test_expired_session_is_finalized(client: TestClient, db_session: Session, monkeypatch):
    as_user("user_a")
    try:
        subject_id = make_subject(client, "Math")
        started = client.post("/study-sessions", json={"subject_id": subject_id, "duration_minutes": 30}).json()
    finally:
        clear_user()

    future = session_service.utcnow() + dt.timedelta(minutes=31)
    monkeypatch.setattr(session_service, "utcnow", lambda: future)

    as_user("user_a")
    try:
        active = client.get("/study-sessions/active").json()
    finally:
        clear_user()

    assert active["active_session"] is None
    from app.models.study_session import SESSION_STATUS_COMPLETED, StudySession

    row = db_session.get(StudySession, __import__("uuid").UUID(started["id"]))
    assert row.status == SESSION_STATUS_COMPLETED


def test_end_session_and_cancel(client: TestClient):
    as_user("user_a")
    try:
        subject_id = make_subject(client, "Math")
        started = client.post("/study-sessions", json={"subject_id": subject_id, "duration_minutes": 30}).json()
        ended = client.post(f"/study-sessions/{started['id']}/end").json()
        # A new session can be started after completion.
        again = client.post("/study-sessions", json={"subject_id": subject_id, "duration_minutes": 20}).json()
        cancelled = client.post(f"/study-sessions/{again['id']}/end", params={"cancel": "true"}).json()
    finally:
        clear_user()
    assert ended["status"] == "completed"
    assert cancelled["status"] == "cancelled"


def test_admin_can_configure_bounds_and_start_uses_them(client: TestClient, db_session: Session):
    # Non-admin is forbidden.
    as_user("student")
    try:
        forbidden = client.put(
            "/admin/study-session-settings", json={"min_minutes": 10, "max_minutes": 20}
        )
    finally:
        clear_user()
    assert forbidden.status_code == 403

    # Promote to admin directly (server-controlled role).
    as_user("boss")
    try:
        client.get("/me")
    finally:
        clear_user()
    admin = db_session.execute(select(Profile).where(Profile.auth_user_id == "boss")).scalar_one()
    admin.role = ROLE_ADMIN
    db_session.commit()

    as_user("boss")
    try:
        updated = client.put(
            "/admin/study-session-settings", json={"min_minutes": 10, "max_minutes": 20}
        )
        subject_id = make_subject(client, "Advanced")
        too_short = client.post(
            "/study-sessions", json={"subject_id": subject_id, "duration_minutes": 5}
        )
        ok = client.post(
            "/study-sessions", json={"subject_id": subject_id, "duration_minutes": 15}
        )
    finally:
        clear_user()

    assert updated.status_code == 200
    assert updated.json() == {"min_minutes": 10, "max_minutes": 20}
    assert too_short.status_code == 422
    assert ok.status_code == 201


def test_audit_events_are_recorded(client: TestClient, db_session: Session):
    as_user("user_a")
    try:
        subject_id = make_subject(client, "Audited")
        client.post("/study-sessions", json={"subject_id": subject_id, "duration_minutes": 30})
    finally:
        clear_user()
    actions = {
        row.action for row in db_session.execute(select(AuditEvent)).scalars().all()
    }
    assert "study_session.started" in actions
