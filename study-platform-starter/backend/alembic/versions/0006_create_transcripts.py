"""create transcript_segments

Revision ID: 0006_create_transcripts
Revises: 0005_create_knowledge
Create Date: 2026-10-14

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_create_transcripts"
down_revision: str | None = "0005_create_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("speaker_label", sa.String(length=120), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_transcript_segments_material_id_materials"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_transcript_segments_subject_id_subjects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcript_segments")),
        sa.UniqueConstraint(
            "material_id", "segment_index", name="uq_transcript_segments_material_index"
        ),
    )
    op.create_index(
        op.f("ix_transcript_segments_material_id"),
        "transcript_segments",
        ["material_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transcript_segments_subject_id"),
        "transcript_segments",
        ["subject_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_transcript_segments_subject_id"), table_name="transcript_segments")
    op.drop_index(op.f("ix_transcript_segments_material_id"), table_name="transcript_segments")
    op.drop_table("transcript_segments")
