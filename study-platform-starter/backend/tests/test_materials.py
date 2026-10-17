from __future__ import annotations

import uuid
from urllib.parse import urlparse

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.supabase import VerifiedIdentity
from app.auth.dependencies import get_identity
from app.main import app
from app.models.audit import AuditEvent
from app.models.material import (
    DUPLICATE_CONFIRMED,
    DUPLICATE_PENDING_REVIEW,
    Material,
    StoredFile,
)
from app.services import materials as material_service
from app.services.rate_limit import InMemoryRateLimiter
from app.storage import get_storage
from app.storage.local import LocalStorageProvider

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def as_user(user_id: str, name: str = "User") -> None:
    app.dependency_overrides[get_identity] = lambda: VerifiedIdentity(
    user_id=user_id, claims={"name": name}
)


def clear_user() -> None:
    app.dependency_overrides.pop(get_identity, None)


def profile_id(client: TestClient) -> str:
    return client.get("/me").json()["id"]


def make_subject(client: TestClient, name: str) -> str:
    return client.post("/subjects", json={"name": name}).json()["id"]


def add_member(client: TestClient, subject_id: str, user_id: str) -> None:
    client.post(f"/subjects/{subject_id}/members", json={"user_id": user_id})


def upload(
    client: TestClient,
    subject_id: str,
    *,
    filename: str = "notes.pdf",
    data: bytes = PDF_BYTES,
    content_type: str = "application/pdf",
    title: str | None = None,
):
    form = {"title": title} if title is not None else None
    return client.post(
        f"/subjects/{subject_id}/materials",
        files={"file": (filename, data, content_type)},
        data=form,
    )


@pytest.fixture()
def storage(tmp_path):
    provider = LocalStorageProvider(
        base_dir=str(tmp_path),
        public_base_url="http://testserver",
        signing_secret="test-secret",
    )
    app.dependency_overrides[get_storage] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.services.rate_limit import get_upload_limiter

    get_upload_limiter().reset()
    yield
    get_upload_limiter().reset()


def test_upload_requires_identity(client: TestClient, storage):
    clear_user()
    response = upload(client, str(uuid.uuid4()))
    assert response.status_code in (401, 403)


def test_non_member_cannot_upload(client: TestClient, storage):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Math")
    finally:
        clear_user()
    as_user("stranger")
    try:
        response = upload(client, subject_id)
    finally:
        clear_user()
    assert response.status_code == 404


def test_member_can_upload_and_list(client: TestClient, storage):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Math")
        response = upload(client, subject_id, title="Lecture 1")
        listing = client.get(f"/subjects/{subject_id}/materials").json()
    finally:
        clear_user()
    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert body["material"]["processing_status"] == "uploaded"
    assert body["material"]["original_filename"] == "notes.pdf"
    assert body["material"]["mime_type"] == "application/pdf"
    assert body["material"]["size_bytes"] == len(PDF_BYTES)
    assert listing["total"] == 1
    assert listing["items"][0]["title"] == "Lecture 1"


def test_unsupported_file_type_is_rejected(client: TestClient, storage):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Math")
        response = upload(client, subject_id, filename="evil.bin", data=b"\x00\x01\x02bogus", content_type="application/octet-stream")
    finally:
        clear_user()
    assert response.status_code == 422


def test_declared_type_mismatch_is_rejected(client: TestClient, storage):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Math")
        response = upload(client, subject_id, filename="fake.pdf", data=PNG_BYTES, content_type="application/pdf")
    finally:
        clear_user()
    assert response.status_code == 422


def test_download_url_is_signed_and_served(client: TestClient, storage):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Math")
        material_id = upload(client, subject_id).json()["material"]["id"]
        download = client.get(f"/materials/{material_id}/download")
        url = download.json()["url"]
    finally:
        clear_user()
    assert download.status_code == 200
    assert download.json()["expires_in"] > 0

    parsed = urlparse(url)
    served = client.get(f"{parsed.path}?{parsed.query}")
    assert served.status_code == 200
    assert served.content == PDF_BYTES


def test_expired_and_tampered_download_urls_are_rejected(client: TestClient, storage):
    expired = client.get("/storage/local/blobs/aa/deadbeef?expires=1&sig=nope")
    assert expired.status_code == 403
    future = client.get("/storage/local/blobs/aa/deadbeef?expires=9999999999&sig=wrong")
    assert future.status_code == 403


def test_exact_duplicate_is_linked_not_re_stored(client: TestClient, db_session: Session, storage):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Math")
        first = upload(client, subject_id, title="Chapter 1")
        second = upload(client, subject_id, title="Copy of chapter 1")
        listing = client.get(f"/subjects/{subject_id}/materials").json()
    finally:
        clear_user()
    assert first.status_code == 201
    assert second.status_code == 200
    body = second.json()
    assert body["created"] is False
    assert body["duplicate"] == "exact"
    assert body["duplicate_material_id"] == first.json()["material"]["id"]
    assert listing["total"] == 1

    stored_count = db_session.execute(select(func.count()).select_from(StoredFile)).scalar_one()
    assert stored_count == 1


def test_cross_subject_privacy(client: TestClient, db_session: Session, storage):
    as_user("alice")
    try:
        subject_a = make_subject(client, "Alice Math")
        material_a = upload(client, subject_a).json()["material"]["id"]
    finally:
        clear_user()

    as_user("bob")
    try:
        subject_b = make_subject(client, "Bob Math")
        # Same bytes in another subject: separate material, no cross-subject signal.
        upload_b = upload(client, subject_b)
        view_a = client.get(f"/materials/{material_a}")
        download_a = client.get(f"/materials/{material_a}/download")
        list_b = client.get(f"/subjects/{subject_b}/materials").json()
    finally:
        clear_user()

    assert upload_b.status_code == 201
    assert upload_b.json()["duplicate"] == "none"
    assert upload_b.json()["duplicate_material_id"] is None
    assert view_a.status_code == 404
    assert download_a.status_code == 404
    assert list_b["total"] == 1
    # Physical bytes are stored once (internal dedupe), but access is per subject.
    stored_count = db_session.execute(select(func.count()).select_from(StoredFile)).scalar_one()
    assert stored_count == 1


def test_similar_content_enters_manual_review(client: TestClient, db_session: Session, storage):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Math")
        upload(client, subject_id, filename="linear algebra notes.pdf", title="linear algebra notes", data=PDF_BYTES + b"A")
        second = upload(client, subject_id, filename="linear algebra note.pdf", title="linear algebra note", data=PDF_BYTES + b"B")
        reviews = client.get(f"/subjects/{subject_id}/duplicate-reviews").json()
    finally:
        clear_user()

    assert second.status_code == 201
    assert second.json()["material"]["duplicate_status"] == DUPLICATE_PENDING_REVIEW
    assert reviews["total"] == 1
    review = reviews["items"][0]
    assert review["status"] == "pending"

    as_user("owner")
    try:
        resolved = client.post(f"/duplicate-reviews/{review['id']}/resolve", json={"decision": "confirm"})
    finally:
        clear_user()
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "confirmed"

    material = db_session.get(Material, uuid.UUID(review["candidate_material_id"]))
    assert material.duplicate_status == DUPLICATE_CONFIRMED


def test_only_owner_resolves_review(client: TestClient, storage):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Math")
        upload(client, subject_id, filename="linear algebra notes.pdf", title="linear algebra notes", data=PDF_BYTES + b"A")
        upload(client, subject_id, filename="linear algebra note.pdf", title="linear algebra note", data=PDF_BYTES + b"B")
        review_id = client.get(f"/subjects/{subject_id}/duplicate-reviews").json()["items"][0]["id"]
    finally:
        clear_user()

    as_user("member")
    try:
        member_profile = profile_id(client)
    finally:
        clear_user()
    as_user("owner")
    try:
        add_member(client, subject_id, member_profile)
    finally:
        clear_user()

    as_user("member")
    try:
        forbidden = client.post(f"/duplicate-reviews/{review_id}/resolve", json={"decision": "dismiss"})
        can_list = client.get(f"/subjects/{subject_id}/duplicate-reviews")
    finally:
        clear_user()
    assert forbidden.status_code == 403
    assert can_list.status_code == 403


def test_delete_permissions(client: TestClient, storage):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Math")
        material_id = upload(client, subject_id).json()["material"]["id"]
    finally:
        clear_user()

    as_user("member")
    try:
        member_profile = profile_id(client)
    finally:
        clear_user()
    as_user("owner")
    try:
        add_member(client, subject_id, member_profile)
    finally:
        clear_user()

    as_user("member")
    try:
        forbidden = client.delete(f"/materials/{material_id}")
    finally:
        clear_user()
    assert forbidden.status_code == 403

    as_user("owner")
    try:
        deleted = client.delete(f"/materials/{material_id}")
        listing = client.get(f"/subjects/{subject_id}/materials").json()
    finally:
        clear_user()
    assert deleted.status_code == 204
    assert listing["total"] == 0


def test_upload_rate_limit(client: TestClient, storage, monkeypatch):
    limiter = InMemoryRateLimiter(limit=2, window_seconds=60)
    monkeypatch.setattr("app.routers.materials.get_upload_limiter", lambda: limiter)
    as_user("owner")
    try:
        subject_id = make_subject(client, "Math")
        upload(client, subject_id, filename="a.pdf", data=PDF_BYTES)
        upload(client, subject_id, filename="b.pdf", data=PDF_BYTES + b"x")
        limited = upload(client, subject_id, filename="c.pdf", data=PDF_BYTES + b"yy")
    finally:
        clear_user()
    assert limited.status_code == 429
    assert limited.headers.get("Retry-After")


def test_audit_events_recorded_for_uploads(client: TestClient, db_session: Session, storage):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Math")
        material_id = upload(client, subject_id).json()["material"]["id"]
        client.get(f"/materials/{material_id}/download")
    finally:
        clear_user()
    actions = {row.action for row in db_session.execute(select(AuditEvent)).scalars().all()}
    assert "material.uploaded" in actions
    assert "material.download_url_issued" in actions


def test_orphan_cleanup_removes_unreferenced_files(db_session: Session, storage):
    import datetime as dt

    stored = StoredFile(
        storage_key="blobs/aa/orphan",
        sha256="a" * 64,
        mime_type="application/pdf",
        size_bytes=3,
        original_filename="orphan.pdf",
    )
    storage.put_object("blobs/aa/orphan", b"abc", content_type="application/pdf")
    db_session.add(stored)
    db_session.commit()

    removed = material_service.cleanup_orphan_stored_files(
        db_session, storage, older_than=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    )
    assert removed == 1
    assert db_session.execute(select(func.count()).select_from(StoredFile)).scalar_one() == 0
