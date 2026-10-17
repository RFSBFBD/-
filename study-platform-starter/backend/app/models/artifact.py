from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Supported study artifact kinds.
ARTIFACT_NOTES = "notes"
ARTIFACT_QUIZ = "quiz"
ARTIFACT_QUIZ_EXPLANATION = "quiz_explanation"
ARTIFACT_REVISION_CARDS = "revision_cards"
ARTIFACT_MIND_MAP = "mind_map"
ARTIFACT_CODE_DESCRIPTIONS = "code_descriptions"
ARTIFACT_CONCEPT_ALIGNMENT = "concept_alignment"
ARTIFACT_TYPES = frozenset(
    {
        ARTIFACT_NOTES,
        ARTIFACT_QUIZ,
        ARTIFACT_QUIZ_EXPLANATION,
        ARTIFACT_REVISION_CARDS,
        ARTIFACT_MIND_MAP,
        ARTIFACT_CODE_DESCRIPTIONS,
        ARTIFACT_CONCEPT_ALIGNMENT,
    }
)

FEEDBACK_UP = "up"
FEEDBACK_DOWN = "down"
FEEDBACK_RATINGS = frozenset({FEEDBACK_UP, FEEDBACK_DOWN})


class GeneratedArtifact(Base):
    """A cached study artifact keyed by its inputs, prompt version, and model.

    The cache key is ``(subject_id, artifact_type, input_hash, prompt_version,
    model_id, settings_hash)`` so identical requests reuse prior output and do
    not spend tokens again. ``subject_id`` is mandatory for scoping and
    authorization.
    """

    __tablename__ = "generated_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("materials.id", ondelete="CASCADE"), nullable=True, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    settings_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "artifact_type",
            "input_hash",
            "prompt_version",
            "model_id",
            "settings_hash",
            name="uq_generated_artifacts_cache",
        ),
        Index("ix_generated_artifacts_subject_type", "subject_id", "artifact_type"),
    )


class ArtifactFeedback(Base):
    """Per-user feedback for a generated artifact (one row per user/artifact)."""

    __tablename__ = "artifact_feedback"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("generated_artifacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rating: Mapped[str] = mapped_column(String(10), nullable=False)
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("artifact_id", "user_id", name="uq_artifact_feedback_user"),
    )


__all__ = [
    "ARTIFACT_CODE_DESCRIPTIONS",
    "ARTIFACT_CONCEPT_ALIGNMENT",
    "ARTIFACT_MIND_MAP",
    "ARTIFACT_NOTES",
    "ARTIFACT_QUIZ",
    "ARTIFACT_QUIZ_EXPLANATION",
    "ARTIFACT_REVISION_CARDS",
    "ARTIFACT_TYPES",
    "ArtifactFeedback",
    "FEEDBACK_DOWN",
    "FEEDBACK_RATINGS",
    "FEEDBACK_UP",
    "GeneratedArtifact",
]
