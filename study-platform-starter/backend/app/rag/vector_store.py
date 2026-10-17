"""Subject-scoped vector store backed by the application database.

Security invariant: ``search`` always filters by ``subject_id`` in the SQL query
itself, before ranking. Callers cannot retrieve another subject's chunks even if
they control the query vector. On PostgreSQL it uses pgvector's cosine distance;
on other dialects (SQLite tests) it computes cosine similarity in Python over the
subject-filtered rows.
"""

from __future__ import annotations

import math
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import RankedDocument, VectorChunk
from app.models.knowledge import KnowledgeChunk


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def _to_ranked(chunk: KnowledgeChunk, score: float) -> RankedDocument:
    provenance = dict(chunk.metadata_json or {})
    provenance.setdefault("chunk_index", chunk.chunk_index)
    return RankedDocument(
        chunk_id=chunk.id,
        material_id=chunk.material_id,
        subject_id=chunk.subject_id,
        content=chunk.content,
        score=score,
        provenance=provenance,
    )


class SqlVectorStore:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(self, chunks: list[VectorChunk]) -> int:
        """Insert chunks idempotently; existing (material, model, hash) are skipped."""
        if not chunks:
            return 0
        existing: set[tuple[uuid.UUID, str, str]] = set()
        material_ids = {chunk.material_id for chunk in chunks}
        model_versions = {chunk.model_version for chunk in chunks}
        rows = self.db.execute(
            select(
                KnowledgeChunk.material_id,
                KnowledgeChunk.model_version,
                KnowledgeChunk.content_hash,
            ).where(
                KnowledgeChunk.material_id.in_(material_ids),
                KnowledgeChunk.model_version.in_(model_versions),
            )
        ).all()
        for material_id, model_version, chunk_hash in rows:
            existing.add((material_id, model_version, chunk_hash))

        inserted = 0
        for chunk in chunks:
            key = (chunk.material_id, chunk.model_version, chunk.content_hash)
            if key in existing:
                continue
            self.db.add(
                KnowledgeChunk(
                    material_id=chunk.material_id,
                    subject_id=chunk.subject_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    token_count=chunk.token_count,
                    embedding=chunk.embedding,
                    model_version=chunk.model_version,
                    metadata_json=chunk.metadata or None,
                )
            )
            existing.add(key)
            inserted += 1
        self.db.flush()
        return inserted

    def search(
        self, *, subject_id: uuid.UUID, query_vector: list[float], top_k: int
    ) -> list[RankedDocument]:
        if top_k <= 0 or not query_vector:
            return []
        dialect = self.db.get_bind().dialect.name
        if dialect == "postgresql":
            distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
            rows = self.db.execute(
                select(KnowledgeChunk, distance)
                .where(
                    KnowledgeChunk.subject_id == subject_id,
                    KnowledgeChunk.embedding.is_not(None),
                )
                .order_by(distance)
                .limit(top_k)
            ).all()
            return [_to_ranked(chunk, 1.0 - float(dist)) for chunk, dist in rows]

        candidate_rows = self.db.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.subject_id == subject_id,
                KnowledgeChunk.embedding.is_not(None),
            )
        ).scalars().all()
        scored = [
            (chunk, _cosine(query_vector, list(chunk.embedding or [])))
            for chunk in candidate_rows
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [_to_ranked(chunk, score) for chunk, score in scored[:top_k]]


__all__ = ["SqlVectorStore"]
