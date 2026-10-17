"""Study artifact generation with caching, citations, and feedback.

Every artifact is subject-scoped and authorized through subject membership. The
model receives numbered sources assembled server-side; citations are built from
those sources (never from model output), so citation integrity is enforced by us.
Generations are cached by ``(subject, artifact_type, input_hash, prompt_version,
model_id, settings_hash)`` to avoid spending tokens twice for identical inputs.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.base import ChatMessage, ChatModel
from app.config import settings
from app.models.artifact import (
    ARTIFACT_CODE_DESCRIPTIONS,
    ARTIFACT_CONCEPT_ALIGNMENT,
    ARTIFACT_MIND_MAP,
    ARTIFACT_NOTES,
    ARTIFACT_QUIZ,
    ARTIFACT_QUIZ_EXPLANATION,
    ARTIFACT_REVISION_CARDS,
    ARTIFACT_TYPES,
    FEEDBACK_RATINGS,
    ArtifactFeedback,
    GeneratedArtifact,
)
from app.models.knowledge import KnowledgeChunk, UsageLog
from app.models.material import Material
from app.models.profile import Profile
from app.models.transcript import TranscriptSegment
from app.services import audit
from app.services import materials as material_service
from app.services import subjects as subject_service

PROMPT_VERSION = "v1"

_JSON_FENCE = re.compile(r"^```[a-zA-Z0-9]*\n|\n```$")


class ArtifactError(Exception):
    status_code = 400


class ArtifactNotFound(ArtifactError):
    status_code = 404


class ArtifactValidationError(ArtifactError):
    status_code = 422


class ArtifactGenerationError(ArtifactError):
    """Model output could not be used (invalid JSON / unexpected shape)."""

    status_code = 502


@dataclass(frozen=True)
class ArtifactResult:
    artifact: GeneratedArtifact
    cached: bool
    citations: list[dict[str, Any]]


@dataclass(frozen=True)
class ArtifactSpec:
    system: str
    instruction: str


_COMMON = (
    "Return ONLY a single valid JSON object. Do not wrap it in markdown fences "
    "or add prose before or after it. Label each point, definition, example, or "
    "explanation with a \"kind\" field set to \"source\" when it is directly "
    "supported by the numbered sources, or \"inference\" when you add your own "
    "explanation. Reference a source with an integer \"citation\" field using the "
    "bracket numbers (for example 1 or 2). Never invent a source that is not in "
    "the list. Use the language of the sources (Arabic, English, or mixed)."
)

_EMPHASIS = (
    "If a source includes timestamps and clearly signals a teacher emphasis "
    "(for example repetition, \"important\", \"note\", \"انتبه\", \"مهم\"), add an "
    "\"emphasis\" entry with the exact phrase, its timestamp_ms from the source "
    "(or null if unknown), a confidence between 0 and 1, and a short evidence "
    "quote. Only include emphasis you can support with evidence; do not guess."
)

ARTIFACT_SPECS: dict[str, ArtifactSpec] = {
    ARTIFACT_NOTES: ArtifactSpec(
        system=(
            "You create detailed, simplified study notes from source material. "
            "Prefer depth over brevity and keep the distinction between the "
            "source content and your own explanations clear." + _EMPHASIS
        ),
        instruction=(
            "Produce JSON of the form {\"title\": string, \"sections\": [{\"heading\": "
            "string, \"points\": [{\"text\": string, \"kind\": \"source\"|\"inference\", "
            "\"citation\": int|null}]}], \"definitions\": [{\"term\": string, "
            "\"definition\": string, \"kind\": string, \"citation\": int|null}], "
            "\"examples\": [{\"text\": string, \"kind\": string, \"citation\": int|null}], "
            "\"emphasis\": [{\"phrase\": string, \"timestamp_ms\": int|null, "
            "\"confidence\": number, \"evidence\": string}]}."
        ),
    ),
    ARTIFACT_QUIZ: ArtifactSpec(
        system="You write fair assessment questions grounded strictly in the sources.",
        instruction=(
            "Produce JSON of the form {\"questions\": [{\"question\": string, "
            "\"choices\": [string, ...], \"answer_index\": int, \"explanation\": string, "
            "\"citation\": int|null}]} with at least three questions."
        ),
    ),
    ARTIFACT_QUIZ_EXPLANATION: ArtifactSpec(
        system="You explain quiz answers clearly and tie them back to the sources.",
        instruction=(
            "Produce JSON of the form {\"explanations\": [{\"question\": string, "
            "\"explanation\": string, \"citation\": int|null}]}."
        ),
    ),
    ARTIFACT_REVISION_CARDS: ArtifactSpec(
        system="You create concise spaced-revision flashcards from the sources.",
        instruction=(
            "Produce JSON of the form {\"cards\": [{\"front\": string, \"back\": string, "
            "\"citation\": int|null}]}."
        ),
    ),
    ARTIFACT_MIND_MAP: ArtifactSpec(
        system="You extract concept structure as a graph of nodes and labelled edges.",
        instruction=(
            "Produce JSON of the form {\"nodes\": [{\"id\": string, \"label\": string}], "
            "\"edges\": [{\"source\": string, \"target\": string, \"label\": string}]}. "
            "Node ids must be referenced consistently by edges."
        ),
    ),
    ARTIFACT_CODE_DESCRIPTIONS: ArtifactSpec(
        system="You describe code and diagrams found in the sources, in plain language.",
        instruction=(
            "Produce JSON of the form {\"snippets\": [{\"language\": string, "
            "\"code\": string, \"description\": string, \"citation\": int|null}]}. "
            "If there is no code or diagram, return an empty snippets list."
        ),
    ),
    ARTIFACT_CONCEPT_ALIGNMENT: ArtifactSpec(
        system=(
            "You compare how multiple sources treat the same concepts, citing each "
            "source by its bracket number and never merging facts across subjects."
        ),
        instruction=(
            "Produce JSON of the form {\"concepts\": [{\"concept\": string, "
            "\"material_ids\": [string], \"sources\": [{\"citation\": int, \"note\": "
            "string}], \"agreements\": [string], \"conflicts\": [string]}]}. Include a "
            "concept only when at least two sources mention it."
        ),
    ),
}


def _mmss(ms: int) -> str:
    total_seconds = max(0, ms // 1000)
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


def _settings_hash(chat_model: ChatModel) -> str:
    payload = {
        "prompt_version": PROMPT_VERSION,
        "model": chat_model.model_id,
        "max_output_tokens": settings.artifact_max_output_tokens,
        "max_source_chars": settings.artifact_max_source_chars,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _input_hash(
    entries: list[dict[str, Any]], artifact_type: str, params: dict[str, Any]
) -> str:
    hasher = hashlib.sha256()
    hasher.update(artifact_type.encode("utf-8"))
    hasher.update(json.dumps(params, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    for entry in entries:
        hasher.update(str(entry["material_id"]).encode("utf-8"))
        hasher.update(entry["kind"].encode("utf-8"))
        hasher.update(str(entry.get("page_number") or "").encode("utf-8"))
        hasher.update(str(entry.get("start_ms") if entry.get("start_ms") is not None else "").encode("utf-8"))
        hasher.update(entry["text"].encode("utf-8"))
    return hasher.hexdigest()


def _collect_sources(db: Session, materials: list[Material]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for material in materials:
        chunks = (
            db.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.material_id == material.id)
                .order_by(KnowledgeChunk.chunk_index.asc())
            )
            .scalars()
            .all()
        )
        for chunk in chunks:
            provenance = chunk.metadata_json or {}
            entries.append(
                {
                    "kind": "chunk",
                    "material_id": material.id,
                    "chunk_id": chunk.id,
                    "title": material.title,
                    "text": chunk.content,
                    "page_number": provenance.get("page_number"),
                    "start_ms": provenance.get("start_ms"),
                    "end_ms": provenance.get("end_ms"),
                }
            )
        segments = (
            db.execute(
                select(TranscriptSegment)
                .where(TranscriptSegment.material_id == material.id)
                .order_by(TranscriptSegment.segment_index.asc())
            )
            .scalars()
            .all()
        )
        for segment in segments:
            entries.append(
                {
                    "kind": "transcript",
                    "material_id": material.id,
                    "chunk_id": None,
                    "title": material.title,
                    "text": segment.text,
                    "page_number": None,
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                }
            )
    return entries


def _build_context(
    entries: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    lines: list[str] = []
    citations: list[dict[str, Any]] = []
    used = 0
    for entry in entries:
        location_bits: list[str] = []
        if entry.get("page_number"):
            location_bits.append(f"page {entry['page_number']}")
        if entry.get("start_ms") is not None:
            location_bits.append(_mmss(int(entry["start_ms"])))
        location = f", {', '.join(location_bits)}" if location_bits else ""
        snippet = entry["text"].strip()
        line = f"[{len(citations) + 1}] ({entry['title']}{location}) {snippet}"
        if used + len(line) > settings.artifact_max_source_chars and citations:
            break
        used += len(line) + 1
        lines.append(line)
        citations.append(
            {
                "index": len(citations) + 1,
                "material_id": str(entry["material_id"]),
                "chunk_id": str(entry["chunk_id"]) if entry.get("chunk_id") else None,
                "title": entry["title"],
                "page_number": entry.get("page_number"),
                "start_ms": entry.get("start_ms"),
                "end_ms": entry.get("end_ms"),
                "snippet": snippet[:400],
            }
        )
    return "\n\n".join(lines), citations


def _parse_json(content: str) -> dict[str, Any]:
    text = _JSON_FENCE.sub("", content.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactGenerationError("The model did not return valid JSON.") from exc
    if not isinstance(data, dict):
        raise ArtifactGenerationError("The model returned an unexpected JSON shape.")
    return data


def _resolve_materials(
    db: Session, user: Profile, subject_id: uuid.UUID, material_ids: list[uuid.UUID]
) -> list[Material]:
    subject_service.get_subject_access(db, subject_id, user)
    materials: list[Material] = []
    seen: set[uuid.UUID] = set()
    for material_id in material_ids:
        if material_id in seen:
            continue
        seen.add(material_id)
        material, _ = material_service.get_material(db, user, material_id)
        if material.subject_id != subject_id:
            raise ArtifactNotFound("Material not found in this subject.")
        materials.append(material)
    return materials


def _find_cached(
    db: Session,
    *,
    subject_id: uuid.UUID,
    artifact_type: str,
    input_hash: str,
    model_id: str,
    settings_hash: str,
) -> GeneratedArtifact | None:
    return (
        db.execute(
            select(GeneratedArtifact).where(
                GeneratedArtifact.subject_id == subject_id,
                GeneratedArtifact.artifact_type == artifact_type,
                GeneratedArtifact.input_hash == input_hash,
                GeneratedArtifact.prompt_version == PROMPT_VERSION,
                GeneratedArtifact.model_id == model_id,
                GeneratedArtifact.settings_hash == settings_hash,
            )
        )
        .scalars()
        .first()
    )


def generate_artifact(
    db: Session,
    chat_model: ChatModel,
    user: Profile,
    *,
    subject_id: uuid.UUID,
    artifact_type: str,
    material_ids: list[uuid.UUID],
    topic: str | None = None,
    language: str | None = None,
    force: bool = False,
) -> ArtifactResult:
    if artifact_type not in ARTIFACT_TYPES:
        raise ArtifactValidationError(f"Unsupported artifact type '{artifact_type}'.")
    if not material_ids:
        raise ArtifactValidationError("At least one material id is required.")

    materials = _resolve_materials(db, user, subject_id, material_ids)
    entries = _collect_sources(db, materials)
    if not entries:
        raise ArtifactValidationError(
            "The selected materials have no indexed or transcribed content yet."
        )

    context, citations = _build_context(entries)
    params = {
        "material_ids": [str(material.id) for material in materials],
        "topic": topic or "",
        "language": language or "",
    }
    input_hash = _input_hash(entries, artifact_type, params)
    settings_hash = _settings_hash(chat_model)
    model_id = chat_model.model_id

    existing = _find_cached(
        db,
        subject_id=subject_id,
        artifact_type=artifact_type,
        input_hash=input_hash,
        model_id=model_id,
        settings_hash=settings_hash,
    )
    if existing is not None and not force:
        return ArtifactResult(
            artifact=existing,
            cached=True,
            citations=list(existing.payload_json.get("citations", [])),
        )

    spec = ARTIFACT_SPECS[artifact_type]
    instruction = spec.instruction
    if topic:
        instruction = f"Focus on: {topic}.\n{instruction}"
    if language:
        instruction = f"Write the output in language code '{language}'.\n{instruction}"
    messages = [
        ChatMessage(role="system", content=f"{spec.system}\n\n{_COMMON}"),
        ChatMessage(
            role="user",
            content=f"Sources:\n{context}\n\nTask:\n{instruction}",
        ),
    ]
    result = chat_model.generate(messages, max_tokens=settings.artifact_max_output_tokens)
    data = _parse_json(result.content)

    payload: dict[str, Any] = {
        "artifact_type": artifact_type,
        "prompt_version": PROMPT_VERSION,
        "topic": topic,
        "data": data,
        "citations": citations,
        "source_material_ids": params["material_ids"],
    }

    if existing is not None:
        existing.payload_json = payload
        existing.model_id = result.model
        existing.user_id = user.id
        db.flush()
        artifact = existing
    else:
        artifact = GeneratedArtifact(
            user_id=user.id,
            subject_id=subject_id,
            material_id=materials[0].id,
            artifact_type=artifact_type,
            input_hash=input_hash,
            prompt_version=PROMPT_VERSION,
            model_id=result.model,
            settings_hash=settings_hash,
            payload_json=payload,
        )
        db.add(artifact)
        db.flush()

    db.add(
        UsageLog(
            user_id=user.id,
            subject_id=subject_id,
            provider="chat",
            model_id=result.model,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            estimated_cost=result.usage.estimated_cost,
            status="success",
        )
    )
    audit.record_event(
        db,
        action="artifact.generated",
        user_id=user.id,
        subject_id=subject_id,
        metadata={"artifact_type": artifact_type, "artifact_id": str(artifact.id)},
        commit=False,
    )
    db.commit()
    db.refresh(artifact)
    return ArtifactResult(artifact=artifact, cached=False, citations=citations)


def get_artifact(db: Session, user: Profile, artifact_id: uuid.UUID) -> GeneratedArtifact:
    artifact = db.get(GeneratedArtifact, artifact_id)
    if artifact is None:
        raise ArtifactNotFound("Artifact not found.")
    subject_service.get_subject_access(db, artifact.subject_id, user)
    return artifact


def list_artifacts(
    db: Session,
    user: Profile,
    *,
    subject_id: uuid.UUID,
    artifact_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[GeneratedArtifact], int]:
    subject_service.get_subject_access(db, subject_id, user)
    conditions = [GeneratedArtifact.subject_id == subject_id]
    if artifact_type:
        conditions.append(GeneratedArtifact.artifact_type == artifact_type)
    base = select(GeneratedArtifact).where(*conditions)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(
            base.order_by(GeneratedArtifact.created_at.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


def add_feedback(
    db: Session,
    user: Profile,
    artifact_id: uuid.UUID,
    *,
    rating: str,
    comment: str | None = None,
) -> ArtifactFeedback:
    if rating not in FEEDBACK_RATINGS:
        raise ArtifactValidationError("Rating must be 'up' or 'down'.")
    artifact = get_artifact(db, user, artifact_id)
    row = (
        db.execute(
            select(ArtifactFeedback).where(
                ArtifactFeedback.artifact_id == artifact.id,
                ArtifactFeedback.user_id == user.id,
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        row = ArtifactFeedback(
            artifact_id=artifact.id,
            user_id=user.id,
            rating=rating,
            comment=(comment or "").strip()[:1000] or None,
        )
        db.add(row)
    else:
        row.rating = rating
        row.comment = (comment or "").strip()[:1000] or None
    audit.record_event(
        db,
        action="artifact.feedback_recorded",
        user_id=user.id,
        subject_id=artifact.subject_id,
        metadata={"artifact_id": str(artifact.id), "rating": rating},
        commit=False,
    )
    db.commit()
    db.refresh(row)
    return row


def list_feedback(db: Session, artifact_id: uuid.UUID) -> list[ArtifactFeedback]:
    return list(
        db.execute(
            select(ArtifactFeedback)
            .where(ArtifactFeedback.artifact_id == artifact_id)
            .order_by(ArtifactFeedback.created_at.asc())
        ).scalars()
    )


__all__ = [
    "ARTIFACT_SPECS",
    "PROMPT_VERSION",
    "ArtifactError",
    "ArtifactGenerationError",
    "ArtifactNotFound",
    "ArtifactResult",
    "ArtifactValidationError",
    "add_feedback",
    "generate_artifact",
    "get_artifact",
    "list_artifacts",
    "list_feedback",
]
