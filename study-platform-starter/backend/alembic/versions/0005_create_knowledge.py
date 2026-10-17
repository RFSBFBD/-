"""create knowledge_chunks and usage_logs

Revision ID: 0005_create_knowledge
Revises: 0004_create_materials
Create Date: 2026-10-13

"""
from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.types import Vector

revision: str = "0005_create_knowledge"
down_revision: str | None = "0004_create_materials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VECTOR_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS") or 1536)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding", Vector(VECTOR_DIMENSIONS), nullable=True),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials.id"], name=op.f("fk_knowledge_chunks_material_id_materials"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_knowledge_chunks_subject_id_subjects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "material_id", "model_version", "content_hash", name="uq_knowledge_chunks_dedupe"
        ),
    )
    op.create_index(op.f("ix_knowledge_chunks_material_id"), "knowledge_chunks", ["material_id"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_subject_id"), "knowledge_chunks", ["subject_id"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_content_hash"), "knowledge_chunks", ["content_hash"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_model_version"), "knowledge_chunks", ["model_version"], unique=False)

    op.create_table(
        "usage_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="success"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"], name=op.f("fk_usage_logs_user_id_profiles"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_usage_logs_subject_id_subjects"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_logs")),
    )
    op.create_index(op.f("ix_usage_logs_user_id"), "usage_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_usage_logs_subject_id"), "usage_logs", ["subject_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_usage_logs_subject_id"), table_name="usage_logs")
    op.drop_index(op.f("ix_usage_logs_user_id"), table_name="usage_logs")
    op.drop_table("usage_logs")

    op.drop_index(op.f("ix_knowledge_chunks_model_version"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_content_hash"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_subject_id"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_material_id"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
