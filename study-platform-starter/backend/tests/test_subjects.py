from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.supabase import VerifiedIdentity
from app.auth.dependencies import get_identity
from app.main import app


def as_user(user_id: str, name: str = "User") -> None:
    app.dependency_overrides[get_identity] = lambda: VerifiedIdentity(
    user_id=user_id, claims={"name": name}
)


def clear_user() -> None:
    app.dependency_overrides.pop(get_identity, None)


def profile_id(client: TestClient) -> str:
    return client.get("/me").json()["id"]


def create_subject(client: TestClient, name: str) -> dict:
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_subject_returns_uuid_and_owner_role(client: TestClient):
    as_user("user_a")
    try:
        subject = create_subject(client, "الرياضيات")
    finally:
        clear_user()
    assert subject["role"] == "owner"
    assert subject["archived_at"] is None
    assert len(subject["id"]) == 36  # UUID string


def test_duplicate_normalized_name_per_owner_conflicts(client: TestClient):
    as_user("user_a")
    try:
        create_subject(client, "Physics")
        duplicate = client.post("/subjects", json={"name": "  physics  "})
    finally:
        clear_user()
    assert duplicate.status_code == 409


def test_different_owners_may_reuse_a_name(client: TestClient):
    as_user("user_a")
    try:
        create_subject(client, "Physics")
    finally:
        clear_user()
    as_user("user_b")
    try:
        response = client.post("/subjects", json={"name": "Physics"})
    finally:
        clear_user()
    assert response.status_code == 201


def test_user_cannot_read_another_users_subject(client: TestClient):
    as_user("user_a")
    try:
        subject = create_subject(client, "Private")
    finally:
        clear_user()
    as_user("user_b")
    try:
        response = client.get(f"/subjects/{subject['id']}")
    finally:
        clear_user()
    assert response.status_code == 404


def test_user_cannot_rename_another_users_subject(client: TestClient):
    as_user("user_a")
    try:
        subject = create_subject(client, "Private")
    finally:
        clear_user()
    as_user("user_b")
    try:
        response = client.patch(f"/subjects/{subject['id']}", json={"name": "Hacked"})
    finally:
        clear_user()
    assert response.status_code == 404


def test_list_pagination_and_archive_filtering(client: TestClient):
    as_user("user_a")
    try:
        for index in range(3):
            create_subject(client, f"Subject {index}")
        first_page = client.get("/subjects", params={"limit": 2, "offset": 0}).json()
        second_page = client.get("/subjects", params={"limit": 2, "offset": 2}).json()
        subject_to_archive = first_page["items"][0]["id"]
        client.post(f"/subjects/{subject_to_archive}/archive")
        active = client.get("/subjects").json()
        archived = client.get("/subjects", params={"include_archived": True}).json()
    finally:
        clear_user()

    assert first_page["total"] == 3
    assert len(first_page["items"]) == 2
    assert len(second_page["items"]) == 1
    assert active["total"] == 2
    assert archived["total"] == 3


def test_archived_subject_cannot_be_renamed_and_can_be_restored(client: TestClient):
    as_user("user_a")
    try:
        subject = create_subject(client, "History")
        client.post(f"/subjects/{subject['id']}/archive")
        rename = client.patch(f"/subjects/{subject['id']}", json={"name": "Ancient"})
        restore = client.post(f"/subjects/{subject['id']}/unarchive")
        rename_after = client.patch(f"/subjects/{subject['id']}", json={"name": "Ancient"})
    finally:
        clear_user()

    assert rename.status_code == 409
    assert restore.status_code == 200
    assert restore.json()["archived_at"] is None
    assert rename_after.status_code == 200


def test_membership_sharing_flow_and_authorization(client: TestClient):
    as_user("user_a")
    try:
        subject = create_subject(client, "Shared")
        user_b_id = None
    finally:
        clear_user()

    as_user("user_b")
    try:
        user_b_id = profile_id(client)
    finally:
        clear_user()

    as_user("user_a")
    try:
        add = client.post(f"/subjects/{subject['id']}/members", json={"user_id": user_b_id})
    finally:
        clear_user()
    assert add.status_code == 201
    assert add.json()["role"] == "member"

    as_user("user_b")
    try:
        can_read = client.get(f"/subjects/{subject['id']}")
        cannot_rename = client.patch(f"/subjects/{subject['id']}", json={"name": "Nope"})
        cannot_add = client.post(
            f"/subjects/{subject['id']}/members", json={"user_id": user_b_id}
        )
    finally:
        clear_user()

    assert can_read.status_code == 200
    assert can_read.json()["role"] == "member"
    assert cannot_rename.status_code == 403
    assert cannot_add.status_code == 403


def test_non_member_cannot_list_members(client: TestClient):
    as_user("user_a")
    try:
        subject = create_subject(client, "Secret")
    finally:
        clear_user()
    as_user("user_c")
    try:
        response = client.get(f"/subjects/{subject['id']}/members")
    finally:
        clear_user()
    assert response.status_code == 404


def test_membership_edge_cases(client: TestClient):
    as_user("user_a")
    try:
        subject = create_subject(client, "Edge")
        user_b_id = profile_id(client)
        owner_role = client.post(
            f"/subjects/{subject['id']}/members", json={"user_id": user_b_id, "role": "owner"}
        )
    finally:
        clear_user()

    # Unknown user cannot be added.
    as_user("user_a")
    try:
        unknown = client.post(
            f"/subjects/{subject['id']}/members",
            json={"user_id": "11111111-1111-1111-1111-111111111111"},
        )
    finally:
        clear_user()

    assert owner_role.status_code == 422
    assert unknown.status_code == 404


def test_owner_cannot_be_removed_and_member_can_be_removed(client: TestClient):
    as_user("user_a")
    try:
        subject = create_subject(client, "Removal")
        owner_id = profile_id(client)
    finally:
        clear_user()

    as_user("user_b")
    try:
        user_b_id = profile_id(client)
    finally:
        clear_user()

    as_user("user_a")
    try:
        client.post(f"/subjects/{subject['id']}/members", json={"user_id": user_b_id})
        remove_owner = client.delete(f"/subjects/{subject['id']}/members/{owner_id}")
        remove_member = client.delete(f"/subjects/{subject['id']}/members/{user_b_id}")
        members_after = client.get(f"/subjects/{subject['id']}/members").json()
    finally:
        clear_user()

    assert remove_owner.status_code == 422
    assert remove_member.status_code == 204
    assert len(members_after) == 1
