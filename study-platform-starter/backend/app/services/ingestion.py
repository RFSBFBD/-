"""Knowledge ingestion: parse -> normalize -> chunk -> embed (cached) -> upsert.

Idempotent: reprocessing the same material reuses chunks (deduped by material,
model version, and content hash) and reuses embeddings cached by content hash, so
no duplicate chunks or redundant embedding calls are produced.

Failures are recorded as a safe ``failed`` processing status; the original file
is never modified and other subjects are unaffected.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import EmbeddingModel, VectorChunk
from app.ai.documents import DocumentParseError, DocumentParser
from app.config import settings
from app.models.knowledge import KnowledgeChunk, UsageLog
from app.models.material import PROCESSING_FAILED, PROCESSING_PROCESSING, PROCESSING_READY
from app.models.profile import Profile
from app.rag.chunking import chunk_document
from app.rag.vector_store import SqlVectorStore
from app.services import audit
from app.services import materials as material_service
from app.storage.base import StorageError, StorageProvider

EMBED_BATCH_SIZE = 64


class IngestionError(Exception):
    status_code = 400


@dataclass(frozen=True)
class IngestionResult:
    material_id: uuid.UUID
    processing_status: str
    chunk_count: int
    embedded_count: int
    cached_count: int
    inserted_count: int


def _model_version(embedding_model: EmbeddingModel) -> str:
    return embedding_model.model_id


def _cached_embeddings(
    db: Session, *, model_version: str, hashes: set[str]
) -> dict[str, list[float]]:
    if not hashes:
        return {}
    rows = db.execute(
        select(KnowledgeChunk.content_hash, KnowledgeChunk.embedding).where(
            KnowledgeChunk.model_version == model_version,
            KnowledgeChunk.content_hash.in_(hashes),
            KnowledgeChunk.embedding.is_not(None),
        )
    ).all()
    cache: dict[str, list[float]] = {}
    for chunk_hash, embedding in rows:
        if embedding is not None and chunk_hash not in cache:
            cache[chunk_hash] = list(embedding)
    return cache


def ingest_material(
    db: Session,
    storage: StorageProvider,
    embedding_model: EmbeddingModel,
    parser: DocumentParser,
    user: Profile,
    material_id: uuid.UUID,
) -> IngestionResult:
    material, stored = material_service.get_material(db, user, material_id)
    material.processing_status = PROCESSING_PROCESSING
    audit.record_event(
        db,
        action="material.ingestion_started",
        user_id=user.id,
        subject_id=material.subject_id,
        metadata={"material_id": str(material.id)},
    )

    try:
        data = storage.get_object(
            stored.storage_key, max_bytes=settings.max_upload_size_mb * 1024 * 1024
        )
        document = parser.parse(
            data, mime_type=stored.mime_type, filename=stored.original_filename
        )
    except (StorageError, DocumentParseError) as exc:
        material.processing_status = PROCESSING_FAILED
        audit.record_event(
            db,
            action="material.ingestion_failed",
            user_id=user.id,
            subject_id=material.subject_id,
            metadata={"material_id": str(material.id), "reason": exc.__class__.__name__},
        )
        raise IngestionError(f"Ingestion failed: {exc}") from exc

    chunks = chunk_document(
        document,
        target_chars=settings.chunk_target_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )
    if not chunks:
        material.processing_status = PROCESSING_FAILED
        audit.record_event(
            db,
            action="material.ingestion_failed",
            user_id=user.id,
            subject_id=material.subject_id,
            metadata={"material_id": str(material.id), "reason": "no_extractable_text"},
        )
        raise IngestionError("Ingestion failed: no extractable text.")

    model_version = _model_version(embedding_model)
    hashes = {chunk.content_hash for chunk in chunks}
    cache = _cached_embeddings(db, model_version=model_version, hashes=hashes)

    to_embed: dict[str, str] = {}
    for chunk in chunks:
        if chunk.content_hash not in cache and chunk.content_hash not in to_embed:
            to_embed[chunk.content_hash] = chunk.content

    embedded_count = 0
    if to_embed:
        keys = list(to_embed.keys())
        for start in range(0, len(keys), EMBED_BATCH_SIZE):
            batch_keys = keys[start : start + EMBED_BATCH_SIZE]
            result = embedding_model.embed([to_embed[key] for key in batch_keys])
            if len(result.vectors) != len(batch_keys):
                raise IngestionError("Embedding provider returned a mismatched vector count.")
            for key, vector in zip(batch_keys, result.vectors):
                cache[key] = vector
            embedded_count += len(batch_keys)
            db.add(
                UsageLog(
                    user_id=user.id,
                    subject_id=material.subject_id,
                    provider="embedding",
                    model_id=result.model,
                    input_tokens=result.usage.input_tokens,
                    status="success",
                )
            )

    vector_chunks = [
        VectorChunk(
            material_id=material.id,
            subject_id=material.subject_id,
            chunk_index=chunk.index,
            content=chunk.content,
            content_hash=chunk.content_hash,
            embedding=cache[chunk.content_hash],
            token_count=chunk.token_count,
            model_version=model_version,
            metadata=chunk.provenance,
        )
        for chunk in chunks
    ]
    inserted = SqlVectorStore(db).upsert(vector_chunks)

    material.processing_status = PROCESSING_READY
    audit.record_event(
        db,
        action="material.ingested",
        user_id=user.id,
        subject_id=material.subject_id,
        metadata={
            "material_id": str(material.id),
            "chunks": len(chunks),
            "inserted": inserted,
            "embedded": embedded_count,
        },
        commit=False,
    )
    db.commit()
    return IngestionResult(
        material_id=material.id,
        processing_status=PROCESSING_READY,
        chunk_count=len(chunks),
        embedded_count=embedded_count,
        cached_count=len(chunks) - embedded_count,
        inserted_count=inserted,
    )


__all__ = ["IngestionError", "IngestionResult", "ingest_material"]
