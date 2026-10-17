from __future__ import annotations

import math
import re
import uuid
import zlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.base import ChatMessage, ChatResult, EmbeddingResult, Usage
from app.auth.supabase import VerifiedIdentity
from app.auth.dependencies import get_identity
from app.main import app
from app.models.artifact import ArtifactFeedback, GeneratedArtifact
from app.routers.rag import get_chat_model_dep, get_embedding_model_dep
from app.storage import get_storage
from app.storage.local import LocalStorageProvider

DIMENSIONS = 128
_WORD = re.compile(r"\w+", re.UNICODE)


class FakeEmbeddingModel:
    model_id = "fake-embed"
    dimensions = DIMENSIONS

    def embed(self, texts: list[str], *, model: str | None = None) -> EmbeddingResult:
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
    def __init__(self, model_id: str = "fake/chat", responder=None) -> None:
        self.model_id = model_id
        self.responder = responder or (lambda messages: '{"data": "ok"}')
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
            content=self.responder(messages),
            model=self.model_id,
            usage=Usage(input_tokens=42, output_tokens=21),
        )


def notes_responder(messages: list[ChatMessage]) -> str:
    return (
        '{"title": "Notes", "sections": [{"heading": "Basics", "points": ['
        '{"text": "Water is H2O.", "kind": "source", "citation": 1}, '
        '{"text": "This matters for life.", "kind": "inference", "citation": null}]}], '
        '"definitions": [], "examples": [], '
        '"emphasis": [{"phrase": "important", "timestamp_ms": null, '
        '"confidence": 0.5, "evidence": "the teacher repeated it"}]}'
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


def use_chat(model: FakeChatModel) -> None:
    app.dependency_overrides[get_chat_model_dep] = lambda: model


def clear_chat() -> None:
    app.dependency_overrides.pop(get_chat_model_dep, None)


def generate(client: TestClient, subject_id: str, artifact_type: str, material_ids, **extra):
    return client.post(
        f"/subjects/{subject_id}/artifacts",
        json={"artifact_type": artifact_type, "material_ids": material_ids, **extra},
    )


def test_notes_distinguish_source_from_inference_and_cite(
    client: TestClient, db_session: Session, storage, embedding_model
):
    use_chat(FakeChatModel(responder=notes_responder))
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "Chemistry")
            material_id = upload_text(
                client,
                subject_id,
                "Water is composed of hydrogen and oxygen atoms.",
                title="Chem",
            )
            ingest(client, subject_id, material_id)
            response = generate(client, subject_id, "notes", [material_id])
        finally:
            clear_user()
    finally:
        clear_chat()

    assert response.status_code == 200
    payload = response.json()
    data = payload["payload"]["data"]
    kinds = [point["kind"] for point in data["sections"][0]["points"]]
    assert "source" in kinds and "inference" in kinds
    assert data["emphasis"][0]["confidence"] == 0.5

    citations = payload["payload"]["citations"]
    assert citations
    assert citations[0]["material_id"] == material_id
    assert "hydrogen and oxygen" in citations[0]["snippet"]
    assert payload["cached"] is False


def test_artifact_is_cached_then_force_regenerates(
    client: TestClient, db_session: Session, storage, embedding_model
):
    model = FakeChatModel(responder=notes_responder)
    use_chat(model)
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "Caching")
            material_id = upload_text(client, subject_id, "Cache me please.", title="c")
            ingest(client, subject_id, material_id)
            first = generate(client, subject_id, "notes", [material_id])
            second = generate(client, subject_id, "notes", [material_id])
            artifact_id = first.json()["id"]
            regenerated = client.post(f"/artifacts/{artifact_id}/regenerate")
        finally:
            clear_user()
    finally:
        clear_chat()

    assert first.status_code == 200 and first.json()["cached"] is False
    assert second.status_code == 200 and second.json()["cached"] is True
    assert second.json()["id"] == first.json()["id"]
    # Cached generation used one model call; regenerate used a second.
    assert len(model.calls) == 2
    assert regenerated.status_code == 200
    assert regenerated.json()["cached"] is False

    count = db_session.execute(select(func.count()).select_from(GeneratedArtifact)).scalar_one()
    assert count == 1


def test_cache_key_invalidates_when_model_changes(
    client: TestClient, db_session: Session, storage, embedding_model
):
    use_chat(FakeChatModel(model_id="fake/chat-a", responder=notes_responder))
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "Invalidate")
            material_id = upload_text(client, subject_id, "Versioned content.", title="v")
            ingest(client, subject_id, material_id)
            first = generate(client, subject_id, "notes", [material_id])
            use_chat(FakeChatModel(model_id="fake/chat-b", responder=notes_responder))
            second = generate(client, subject_id, "notes", [material_id])
        finally:
            clear_user()
    finally:
        clear_chat()

    assert first.json()["id"] != second.json()["id"]
    assert first.json()["cached"] is False and second.json()["cached"] is False
    count = db_session.execute(select(func.count()).select_from(GeneratedArtifact)).scalar_one()
    assert count == 2


def test_citations_never_leak_cross_subject(
    client: TestClient, db_session: Session, storage, embedding_model
):
    use_chat(FakeChatModel(responder=notes_responder))
    try:
        as_user("alice")
        try:
            subject_a = make_subject(client, "Alice Notes")
            material_a = upload_text(client, subject_a, "Alpha topic only.", title="A")
            ingest(client, subject_a, material_a)
        finally:
            clear_user()

        as_user("bob")
        try:
            subject_b = make_subject(client, "Bob Notes")
            material_b = upload_text(
                client, subject_b, "SECRET_PHRASE_ZEBRA lives here.", title="B"
            )
            ingest(client, subject_b, material_b)
        finally:
            clear_user()

        as_user("alice")
        try:
            response = generate(client, subject_a, "notes", [material_a])
            forbidden = client.post(
                f"/subjects/{subject_b}/artifacts",
                json={"artifact_type": "notes", "material_ids": [material_b]},
            )
        finally:
            clear_user()
    finally:
        clear_chat()

    assert response.status_code == 200
    payload = response.json()["payload"]
    for citation in payload["citations"]:
        assert citation["material_id"] != material_b
        assert "SECRET_PHRASE_ZEBRA" not in citation["snippet"]
    assert forbidden.status_code == 404


def test_invalid_model_json_is_rejected(client: TestClient, db_session: Session, storage, embedding_model):
    use_chat(FakeChatModel(responder=lambda messages: "not json at all"))
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "Bad JSON")
            material_id = upload_text(client, subject_id, "Some content.", title="x")
            ingest(client, subject_id, material_id)
            response = generate(client, subject_id, "notes", [material_id])
        finally:
            clear_user()
    finally:
        clear_chat()

    assert response.status_code == 502
    count = db_session.execute(select(func.count()).select_from(GeneratedArtifact)).scalar_one()
    assert count == 0


def test_material_without_sources_is_rejected(client: TestClient, storage, embedding_model):
    use_chat(FakeChatModel(responder=notes_responder))
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "Empty Sources")
            material_id = upload_text(client, subject_id, "Not ingested.", title="n")
            response = generate(client, subject_id, "notes", [material_id])
        finally:
            clear_user()
    finally:
        clear_chat()
    assert response.status_code == 422


def test_non_member_cannot_generate(client: TestClient, storage, embedding_model):
    use_chat(FakeChatModel(responder=notes_responder))
    try:
        as_user("alice")
        try:
            subject_a = make_subject(client, "Alice Private")
            material_a = upload_text(client, subject_a, "Private content.", title="p")
            ingest(client, subject_a, material_a)
        finally:
            clear_user()

        as_user("bob")
        try:
            response = generate(client, subject_a, "notes", [material_a])
        finally:
            clear_user()
    finally:
        clear_chat()
    assert response.status_code == 404


def test_feedback_can_be_updated(client: TestClient, db_session: Session, storage, embedding_model):
    use_chat(FakeChatModel(responder=notes_responder))
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "Feedback")
            material_id = upload_text(client, subject_id, "Feedback content.", title="f")
            ingest(client, subject_id, material_id)
            artifact_id = generate(client, subject_id, "notes", [material_id]).json()["id"]
            up = client.post(f"/artifacts/{artifact_id}/feedback", json={"rating": "up"})
            down = client.post(
                f"/artifacts/{artifact_id}/feedback",
                json={"rating": "down", "comment": "needs more detail"},
            )
            invalid = client.post(f"/artifacts/{artifact_id}/feedback", json={"rating": "meh"})
        finally:
            clear_user()
    finally:
        clear_chat()

    assert up.status_code == 200
    assert down.status_code == 200
    assert down.json()["rating"] == "down"
    assert down.json()["comment"] == "needs more detail"
    assert invalid.status_code == 422
    count = db_session.execute(select(func.count()).select_from(ArtifactFeedback)).scalar_one()
    assert count == 1


def test_multiple_artifact_types_and_concept_alignment(
    client: TestClient, db_session: Session, storage, embedding_model
):
    def responder(messages: list[ChatMessage]) -> str:
        instruction = messages[-1].content
        if "questions" in instruction:
            return '{"questions": [{"question": "Q1?", "choices": ["a", "b"], "answer_index": 1, "explanation": "because", "citation": 1}]}'
        if "nodes" in instruction:
            return '{"nodes": [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}], "edges": [{"source": "n1", "target": "n2", "label": "rel"}]}'
        if "concepts" in instruction:
            return '{"concepts": [{"concept": "water", "material_ids": ["x"], "sources": [{"citation": 1, "note": "n"}], "agreements": [], "conflicts": []}]}'
        return '{"cards": [{"front": "f", "back": "b", "citation": 1}]}'

    use_chat(FakeChatModel(responder=responder))
    try:
        as_user("owner")
        try:
            subject_id = make_subject(client, "Mixed Types")
            material_id = upload_text(
                client, subject_id, "Water is H2O. Water matters for life.", title="w"
            )
            ingest(client, subject_id, material_id)
            quiz = generate(client, subject_id, "quiz", [material_id])
            mind_map = generate(client, subject_id, "mind_map", [material_id])
            cards = generate(client, subject_id, "revision_cards", [material_id])
            alignment = generate(client, subject_id, "concept_alignment", [material_id])
            listing = client.get(f"/subjects/{subject_id}/artifacts")
        finally:
            clear_user()
    finally:
        clear_chat()

    assert quiz.status_code == 200
    assert quiz.json()["payload"]["data"]["questions"][0]["answer_index"] == 1
    assert mind_map.json()["payload"]["data"]["edges"][0]["label"] == "rel"
    assert cards.json()["payload"]["data"]["cards"][0]["front"] == "f"
    assert alignment.json()["payload"]["data"]["concepts"][0]["concept"] == "water"
    assert listing.status_code == 200
    assert listing.json()["total"] == 4
