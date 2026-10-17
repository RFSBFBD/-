from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Material processing lifecycle.
PROCESSING_UPLOADED = "uploaded"
PROCESSING_PROCESSING = "processing"
PROCESSING_READY = "ready"
PROCESSING_FAILED = "failed"
PROCESSING_STATUSES = frozenset(
    {PROCESSING_UPLOADED, PROCESSING_PROCESSING, PROCESSING_READY, PROCESSING_FAILED}
)

# Duplicate classification for a material.
DUPLICATE_NONE = "none"
DUPLICATE_EXACT = "exact"
DUPLICATE_PENDING_REVIEW = "pending_review"
DUPLICATE_CONFIRMED = "confirmed"
DUPLICATE_DISMISSED = "dismissed"
DUPLICATE_STATUSES = frozenset(
    {
        DUPLICATE_NONE,
        DUPLICATE_EXACT,
        DUPLICATE_PENDING_REVIEW,
        DUPLICATE_CONFIRMED,
        DUPLICATE_DISMISSED,
    }
)

# Manual review lifecycle for similar-but-not-identical candidates.
REVIEW_PENDING = "pending"
REVIEW_CONFIRMED = "confirmed"
REVIEW_DISMISSED = "dismissed"
REVIEW_STATUSES = frozenset({REVIEW_PENDING, REVIEW_CONFIRMED, REVIEW_DISMISSED})


class StoredFile(Base):
    """Content-addressed physical file registry.

    Bytes are stored once per SHA-256 where feasible; subject-private access is
    enforced at the ``materials`` link, never here.
    """

    __tablename__ = "stored_files"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    uploader_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Material(Base):
    """Subject-scoped link that grants members access to a stored file."""

    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stored_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("stored_files.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uploader_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    material_type: Mapped[str] = mapped_column(String(30), nullable=False, default="other")
    processing_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=PROCESSING_UPLOADED, index=True
    )
    duplicate_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=DUPLICATE_NONE, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_materials_subject_active", "subject_id", "deleted_at"),)


class DuplicateReview(Base):
    """Manual review for similar-but-not-identical content within a subject.

    Similarity never auto-deletes or auto-rejects; a human resolves it.
    """

    __tablename__ = "duplicate_reviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_material_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    matched_material_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=REVIEW_PENDING, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
