"""create generated_artifacts and artifact_feedback

Revision ID: 0007_create_artifacts
Revises: 0006_create_transcripts
Create Date: 2026-10-14

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_create_artifacts"
down_revision: str | None = "0006_create_transcripts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generated_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("settings_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"],
            name=op.f("fk_generated_artifacts_user_id_profiles"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"],
            name=op.f("fk_generated_artifacts_subject_id_subjects"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials.id"],
            name=op.f("fk_generated_artifacts_material_id_materials"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generated_artifacts")),
        sa.UniqueConstraint(
            "subject_id",
            "artifact_type",
            "input_hash",
            "prompt_version",
            "model_id",
            "settings_hash",
            name="uq_generated_artifacts_cache",
        ),
    )
    op.create_index(
        op.f("ix_generated_artifacts_user_id"), "generated_artifacts", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_generated_artifacts_subject_id"),
        "generated_artifacts",
        ["subject_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_artifacts_material_id"),
        "generated_artifacts",
        ["material_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_artifacts_artifact_type"),
        "generated_artifacts",
        ["artifact_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_artifacts_input_hash"),
        "generated_artifacts",
        ["input_hash"],
        unique=False,
    )
    op.create_index(
        "ix_generated_artifacts_subject_type",
        "generated_artifacts",
        ["subject_id", "artifact_type"],
        unique=False,
    )

    op.create_table(
        "artifact_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("rating", sa.String(length=10), nullable=False),
        sa.Column("comment", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["generated_artifacts.id"],
            name=op.f("fk_artifact_feedback_artifact_id_generated_artifacts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"],
            name=op.f("fk_artifact_feedback_user_id_profiles"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifact_feedback")),
        sa.UniqueConstraint("artifact_id", "user_id", name="uq_artifact_feedback_user"),
    )
    op.create_index(
        op.f("ix_artifact_feedback_artifact_id"),
        "artifact_feedback",
        ["artifact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_artifact_feedback_user_id"), "artifact_feedback", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_artifact_feedback_user_id"), table_name="artifact_feedback")
    op.drop_index(op.f("ix_artifact_feedback_artifact_id"), table_name="artifact_feedback")
    op.drop_table("artifact_feedback")

    op.drop_index("ix_generated_artifacts_subject_type", table_name="generated_artifacts")
    op.drop_index(op.f("ix_generated_artifacts_input_hash"), table_name="generated_artifacts")
    op.drop_index(op.f("ix_generated_artifacts_artifact_type"), table_name="generated_artifacts")
    op.drop_index(op.f("ix_generated_artifacts_material_id"), table_name="generated_artifacts")
    op.drop_index(op.f("ix_generated_artifacts_subject_id"), table_name="generated_artifacts")
    op.drop_index(op.f("ix_generated_artifacts_user_id"), table_name="generated_artifacts")
    op.drop_table("generated_artifacts")
