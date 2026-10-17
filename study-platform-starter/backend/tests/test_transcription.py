from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.base import ParsedPage
from app.ai.transcription import TranscriptionError
from app.auth.supabase import VerifiedIdentity
from app.auth.dependencies import get_identity
from app.main import app
from app.models.knowledge import UsageLog
from app.models.material import Material
from app.models.transcript import TranscriptSegment
from app.routers.transcription import get_transcription_provider_dep
from app.storage import get_storage
from app.storage.local import LocalStorageProvider


def audio_bytes() -> bytes:
    return b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 128


def sample_pages() -> list[ParsedPage]:
    return [
        ParsedPage(
            page_number=None,
            text="الخوارزمية هي مجموعة من الخطوات المنطقية لحل مشكلة.",
            start_ms=0,
            end_ms=1500,
            metadata={"language": "ar", "confidence": 0.91},
        ),
        ParsedPage(
            page_number=None,
            text="Machine learning تعلم الآلة is a branch of artificial intelligence.",
            start_ms=1500,
            end_ms=3200,
            metadata={"language": "ar", "confidence": 0.83},
        ),
    ]


class FakeTranscriptionProvider:
    model_id = "fake-whisper"

    def __init__(self, pages=None, error: Exception | None = None) -> None:
        self.pages = pages if pages is not None else sample_pages()
        self.error = error
        self.calls: list[dict] = []

    def transcribe(self, data: bytes, *, filename: str, language: str | None = None):
        self.calls.append({"filename": filename, "language": language})
        if self.error is not None:
            raise self.error
        return self.pages


def as_user(user_id: str, name: str = "User") -> None:
    app.dependency_overrides[get_identity] = lambda: VerifiedIdentity(
        user_id=user_id, claims={"name": name}
    )


def clear_user() -> None:
    app.dependency_overrides.pop(get_identity, None)


def make_subject(client: TestClient, name: str) -> str:
    return client.post("/subjects", json={"name": name}).json()["id"]


def upload_audio(client: TestClient, subject_id: str, *, title: str = "Lecture") -> str:
    return client.post(
        f"/subjects/{subject_id}/materials",
        files={"file": ("lecture.wav", audio_bytes(), "audio/wav")},
        data={"title": title},
    ).json()["material"]["id"]


def upload_text(client: TestClient, subject_id: str, text: str) -> str:
    return client.post(
        f"/subjects/{subject_id}/materials",
        files={"file": ("notes.txt", text.encode("utf-8"), "text/plain")},
        data={"title": "Notes"},
    ).json()["material"]["id"]


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


def use_provider(provider: FakeTranscriptionProvider) -> None:
    app.dependency_overrides[get_transcription_provider_dep] = lambda: provider


def clear_provider() -> None:
    app.dependency_overrides.pop(get_transcription_provider_dep, None)


def test_audio_transcription_preserves_timestamps_and_is_idempotent(
    client: TestClient, db_session: Session, storage
):
    provider = FakeTranscriptionProvider()
    use_provider(provider)
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "Physics")
            material_id = upload_audio(client, subject_id)
            first = client.post(f"/subjects/{subject_id}/materials/{material_id}/transcribe")
            second = client.post(f"/subjects/{subject_id}/materials/{material_id}/transcribe")
            transcript = client.get(
                f"/subjects/{subject_id}/materials/{material_id}/transcript"
            )
        finally:
            clear_user()
    finally:
        clear_provider()

    assert first.status_code == 200
    body = first.json()
    assert body["processing_status"] == "ready"
    assert body["segment_count"] == 2
    assert body["model"] == "fake-whisper"
    assert body["detected_language"] == "ar"

    assert second.status_code == 200
    assert second.json()["segment_count"] == 2

    # Re-transcribing replaces instead of duplicating.
    count = db_session.execute(select(func.count()).select_from(TranscriptSegment)).scalar_one()
    assert count == 2

    payload = transcript.json()
    assert payload["total"] == 2
    starts = [segment["start_ms"] for segment in payload["segments"]]
    ends = [segment["end_ms"] for segment in payload["segments"]]
    assert starts == sorted(starts)
    for start, end in zip(starts, ends):
        assert start >= 0
        assert end >= start
    assert "الخوارزمية" in payload["segments"][0]["text"]
    assert "Machine learning" in payload["segments"][1]["text"]

    providers = {
        row.provider for row in db_session.execute(select(UsageLog)).scalars().all()
    }
    assert "transcription" in providers


def test_non_audio_material_is_rejected(client: TestClient, storage):
    use_provider(FakeTranscriptionProvider())
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "Texts")
            material_id = upload_text(client, subject_id, "plain text content")
            response = client.post(
                f"/subjects/{subject_id}/materials/{material_id}/transcribe"
            )
        finally:
            clear_user()
    finally:
        clear_provider()
    assert response.status_code == 422


def test_missing_provider_returns_503(client: TestClient, storage):
    as_user("owner")
    try:
        subject_id = make_subject(client, "NoWhisper")
        material_id = upload_audio(client, subject_id)
        response = client.post(f"/subjects/{subject_id}/materials/{material_id}/transcribe")
    finally:
        clear_user()
    assert response.status_code == 503


def test_invalid_timestamps_mark_material_failed(
    client: TestClient, db_session: Session, storage
):
    bad = FakeTranscriptionProvider(
        pages=[
            ParsedPage(
                page_number=None, text="bad", start_ms=5000, end_ms=1000, metadata={}
            )
        ]
    )
    use_provider(bad)
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "BadTiming")
            material_id = upload_audio(client, subject_id)
            response = client.post(
                f"/subjects/{subject_id}/materials/{material_id}/transcribe"
            )
        finally:
            clear_user()
    finally:
        clear_provider()

    assert response.status_code == 502
    segments = db_session.execute(select(func.count()).select_from(TranscriptSegment)).scalar_one()
    assert segments == 0
    material = db_session.get(Material, uuid.UUID(material_id))
    assert material.processing_status == "failed"


def test_provider_failure_is_recovered_safely(client: TestClient, db_session: Session, storage):
    failing = FakeTranscriptionProvider(error=TranscriptionError("engine boom"))
    use_provider(failing)
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "Boom")
            material_id = upload_audio(client, subject_id)
            response = client.post(
                f"/subjects/{subject_id}/materials/{material_id}/transcribe"
            )
        finally:
            clear_user()
    finally:
        clear_provider()

    assert response.status_code == 503
    segments = db_session.execute(select(func.count()).select_from(TranscriptSegment)).scalar_one()
    assert segments == 0
    material = db_session.get(Material, uuid.UUID(material_id))
    assert material.processing_status == "failed"


def test_cross_subject_transcript_is_not_accessible(client: TestClient, storage):
    use_provider(FakeTranscriptionProvider())
    try:
        as_user("alice")
        try:
            subject_a = make_subject(client, "Alice Audio")
            material_a = upload_audio(client, subject_a)
            client.post(f"/subjects/{subject_a}/materials/{material_a}/transcribe")
        finally:
            clear_user()

        as_user("bob")
        try:
            subject_b = make_subject(client, "Bob Audio")
            # Bob cannot read Alice's transcript...
            read = client.get(f"/subjects/{subject_a}/materials/{material_a}/transcript")
            # ...nor transcribe it under his own subject id.
            transcribe = client.post(
                f"/subjects/{subject_b}/materials/{material_a}/transcribe"
            )
        finally:
            clear_user()
    finally:
        clear_provider()

    assert read.status_code == 404
    assert transcribe.status_code == 404
