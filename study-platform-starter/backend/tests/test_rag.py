from __future__ import annotations

import math
import re
import uuid
import zlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    Usage,
    VectorChunk,
)
from app.auth.supabase import VerifiedIdentity
from app.auth.dependencies import get_identity
from app.main import app
from app.models.knowledge import KnowledgeChunk, UsageLog
from app.rag.vector_store import SqlVectorStore
from app.routers.rag import get_chat_model_dep, get_embedding_model_dep
from app.storage import get_storage
from app.storage.local import LocalStorageProvider

DIMENSIONS = 256
_WORD = re.compile(r"\w+", re.UNICODE)


class FakeEmbeddingModel:
    model_id = "fake-embed"
    dimensions = DIMENSIONS

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str], *, model: str | None = None) -> EmbeddingResult:
        self.calls.append(list(texts))
        return EmbeddingResult(
            vectors=[self._vector(text) for text in texts],
            model=self.model_id,
            dimensions=DIMENSIONS,
            usage=Usage(input_tokens=sum(len(t) for t in texts) // 4),
        )

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * DIMENSIONS
        for token in _WORD.findall(text.casefold()):
            vector[zlib.crc32(token.encode("utf-8")) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class FakeChatModel:
    model_id = "fake/chat"

    def __init__(self, reply: str = "Grounded answer citing [1].") -> None:
        self.reply = reply
        self.calls: list[list[ChatMessage]] = []

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        self.calls.append(list(messages))
        return ChatResult(
            content=self.reply,
            model=self.model_id,
            usage=Usage(input_tokens=11, output_tokens=7),
        )


def as_user(user_id: str, name: str = "User") -> None:
    app.dependency_overrides[get_identity] = lambda: VerifiedIdentity(
    user_id=user_id, claims={"name": name}
)


def clear_user() -> None:
    app.dependency_overrides.pop(get_identity, None)


def make_subject(client: TestClient, name: str) -> str:
    return client.post("/subjects", json={"name": name}).json()["id"]


def upload_text(client: TestClient, subject_id: str, text: str, *, title: str) -> str:
    return client.post(
        f"/subjects/{subject_id}/materials",
        files={"file": ("notes.txt", text.encode("utf-8"), "text/plain")},
        data={"title": title},
    ).json()["material"]["id"]


def ingest(client: TestClient, subject_id: str, material_id: str):
    return client.post(f"/subjects/{subject_id}/materials/{material_id}/ingest")


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


@pytest.fixture()
def embedding_model() -> FakeEmbeddingModel:
    model = FakeEmbeddingModel()
    app.dependency_overrides[get_embedding_model_dep] = lambda: model
    yield model
    app.dependency_overrides.pop(get_embedding_model_dep, None)


@pytest.fixture()
def chat_model() -> FakeChatModel:
    model = FakeChatModel()
    app.dependency_overrides[get_chat_model_dep] = lambda: model
    yield model
    app.dependency_overrides.pop(get_chat_model_dep, None)


def test_ingestion_chunks_and_is_idempotent(
    client: TestClient, db_session: Session, storage, embedding_model
):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Biology")
        material_id = upload_text(
            client,
            subject_id,
            "Photosynthesis converts light into chemical energy. "
            "Chlorophyll absorbs light. Reactive oxygen is produced. " * 20,
            title="Biology notes",
        )
        first = ingest(client, subject_id, material_id)
        second = ingest(client, subject_id, material_id)
    finally:
        clear_user()

    assert first.status_code == 200
    body = first.json()
    assert body["processing_status"] == "ready"
    assert body["chunk_count"] >= 1
    assert body["embedded_count"] == body["chunk_count"]
    assert body["inserted_count"] == body["chunk_count"]

    assert second.status_code == 200
    second_body = second.json()
    assert second_body["inserted_count"] == 0
    assert second_body["embedded_count"] == 0
    assert second_body["chunk_count"] == body["chunk_count"]

    stored = db_session.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one()
    assert stored == body["chunk_count"]
    # Embeddings generated once for the unique content, then served from cache.
    assert len(embedding_model.calls) == 1


def test_cross_subject_secret_is_never_retrieved_or_cited(
    client: TestClient, db_session: Session, storage, embedding_model, chat_model
):
    as_user("alice")
    try:
        subject_a = make_subject(client, "Alice Physics")
        material_a = upload_text(
            client, subject_a, "Newton's laws describe motion and force.", title="Physics"
        )
        ingest(client, subject_a, material_a)
    finally:
        clear_user()

    as_user("bob")
    try:
        subject_b = make_subject(client, "Bob Physics")
        material_b = upload_text(
            client,
            subject_b,
            "The SECRET_PHRASE_ZEBRA is only in subject B and must never leak.",
            title="Secret",
        )
        ingest(client, subject_b, material_b)
    finally:
        clear_user()

    as_user("alice")
    try:
        response = client.post(
            f"/subjects/{subject_a}/ask", json={"question": "What is SECRET_PHRASE_ZEBRA?"}
        )
        foreign = client.post(f"/subjects/{subject_b}/ask", json={"question": "hi"})
    finally:
        clear_user()

    assert response.status_code == 200
    payload = response.json()
    material_b_uuid = str(uuid.UUID(material_b))
    for citation in payload["citations"]:
        assert citation["material_id"] != material_b_uuid
        assert "SECRET_PHRASE_ZEBRA" not in citation["snippet"]
    assert foreign.status_code == 404

    # The database itself never returns another subject's chunks.
    store = SqlVectorStore(db_session)
    results = store.search(
        subject_id=uuid.UUID(subject_a),
        query_vector=FakeEmbeddingModel._vector("SECRET_PHRASE_ZEBRA"),
        top_k=10,
    )
    assert all("SECRET_PHRASE_ZEBRA" not in document.content for document in results)


def test_answer_uses_sources_and_logs_usage(
    client: TestClient, db_session: Session, storage, embedding_model, chat_model
):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Chemistry")
        material_id = upload_text(
            client,
            subject_id,
            "Water is composed of hydrogen and oxygen atoms.",
            title="Chemistry",
        )
        ingest(client, subject_id, material_id)
        response = client.post(
            f"/subjects/{subject_id}/ask", json={"question": "What is water made of?"}
        )
    finally:
        clear_user()

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_context"] is True
    assert payload["answer"]
    assert payload["citations"]
    assert payload["citations"][0]["material_id"] == material_id
    # The retrieved source text is included in the prompt sent to the model.
    assert "hydrogen and oxygen" in chat_model.calls[0][1].content

    providers = {
        row.provider
        for row in db_session.execute(select(UsageLog)).scalars().all()
    }
    assert {"embedding", "chat"}.issubset(providers)


def test_answer_without_sources_short_circuits(
    client: TestClient, storage, embedding_model, chat_model
):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Empty")
        response = client.post(f"/subjects/{subject_id}/ask", json={"question": "Anything?"})
    finally:
        clear_user()

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_context"] is False
    assert payload["citations"] == []
    assert chat_model.calls == []


def test_ingest_missing_provider_returns_503(client: TestClient, storage):
    from fastapi import HTTPException

    def unavailable():
        raise HTTPException(status_code=503, detail="no embeddings")

    app.dependency_overrides[get_embedding_model_dep] = unavailable
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "NoAI")
            material_id = upload_text(client, subject_id, "text", title="t")
            response = ingest(client, subject_id, material_id)
        finally:
            clear_user()
    finally:
        app.dependency_overrides.pop(get_embedding_model_dep, None)
    assert response.status_code == 503


def test_multilingual_fixtures_retrieve_matching_language(
    client: TestClient, storage, embedding_model, chat_model
):
    as_user("owner")
    try:
        subject_id = make_subject(client, "Languages")
        arabic = upload_text(
            client,
            subject_id,
            "الخوارزمية هي مجموعة من الخطوات المنطقية لحل مشكلة معينة.",
            title="عربي",
        )
        english = upload_text(
            client,
            subject_id,
            "An algorithm is a finite sequence of well-defined instructions.",
            title="English",
        )
        mixed = upload_text(
            client,
            subject_id,
            "Machine learning تعلم الآلة is a branch of artificial intelligence.",
            title="Mixed",
        )
        for material_id in (arabic, english, mixed):
            ingest(client, subject_id, material_id)
        arabic_answer = client.post(
            f"/subjects/{subject_id}/ask", json={"question": "ما هي الخوارزمية؟"}
        )
        english_answer = client.post(
            f"/subjects/{subject_id}/ask",
            json={"question": "What is an algorithm instruction sequence?"},
        )
    finally:
        clear_user()

    assert arabic_answer.status_code == 200
    assert english_answer.status_code == 200
    assert arabic_answer.json()["citations"][0]["material_id"] == arabic
    assert english_answer.json()["citations"][0]["material_id"] == english


def test_vector_store_search_filters_by_subject(db_session: Session):
    from app.models.material import Material, StoredFile

    stored = StoredFile(
        storage_key="blobs/aa/x",
        sha256="a" * 64,
        mime_type="text/plain",
        size_bytes=1,
        original_filename="x.txt",
    )
    db_session.add(stored)
    db_session.flush()

    subject_a = uuid.uuid4()
    subject_b = uuid.uuid4()
    db_session.add_all(
        [
            KnowledgeChunk(
                material_id=_material(db_session, stored, subject_a),
                subject_id=subject_a,
                chunk_index=0,
                content="alpha",
                content_hash="h1",
                embedding=_one_hot(0),
                model_version="m",
            ),
            KnowledgeChunk(
                material_id=_material(db_session, stored, subject_b),
                subject_id=subject_b,
                chunk_index=0,
                content="beta",
                content_hash="h2",
                embedding=_one_hot(1),
                model_version="m",
            ),
        ]
    )
    db_session.flush()

    results = SqlVectorStore(db_session).search(
        subject_id=subject_a, query_vector=_one_hot(0), top_k=5
    )
    assert len(results) == 1
    assert results[0].subject_id == subject_a
    assert results[0].content == "alpha"


def test_upsert_is_idempotent(db_session: Session):
    subject_id = uuid.uuid4()
    material_id = uuid.uuid4()
    store = SqlVectorStore(db_session)
    chunk = VectorChunk(
        material_id=material_id,
        subject_id=subject_id,
        chunk_index=0,
        content="same",
        content_hash="same-hash",
        embedding=_one_hot(0),
        token_count=1,
        model_version="m",
    )
    assert store.upsert([chunk]) == 1
    assert store.upsert([chunk]) == 0
    stored = db_session.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one()
    assert stored == 1


def _one_hot(index: int) -> list[float]:
    vector = [0.0] * DIMENSIONS
    vector[index] = 1.0
    return vector


def _material(db: Session, stored: StoredFile, subject_id: uuid.UUID) -> uuid.UUID:
    from app.models.material import Material

    material = Material(subject_id=subject_id, stored_file_id=stored.id, title="t")
    db.add(material)
    db.flush()
    return material.id
