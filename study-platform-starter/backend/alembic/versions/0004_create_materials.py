"""create stored_files, materials, duplicate_reviews

Revision ID: 0004_create_materials
Revises: 0003_create_study_sessions
Create Date: 2026-10-13

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_create_materials"
down_revision: str | None = "0003_create_study_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("uploader_id", sa.Uuid(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["uploader_id"], ["profiles.id"], name=op.f("fk_stored_files_uploader_id_profiles"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_files")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_stored_files_storage_key")),
    )
    op.create_index(op.f("ix_stored_files_uploader_id"), "stored_files", ["uploader_id"], unique=False)
    op.create_index(op.f("ix_stored_files_sha256"), "stored_files", ["sha256"], unique=False)

    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("stored_file_id", sa.Uuid(), nullable=False),
        sa.Column("uploader_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("material_type", sa.String(length=30), nullable=False, server_default="other"),
        sa.Column("processing_status", sa.String(length=30), nullable=False, server_default="uploaded"),
        sa.Column("duplicate_status", sa.String(length=30), nullable=False, server_default="none"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_materials_subject_id_subjects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["stored_file_id"], ["stored_files.id"], name=op.f("fk_materials_stored_file_id_stored_files"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["uploader_id"], ["profiles.id"], name=op.f("fk_materials_uploader_id_profiles"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_materials")),
    )
    op.create_index(op.f("ix_materials_subject_id"), "materials", ["subject_id"], unique=False)
    op.create_index(op.f("ix_materials_stored_file_id"), "materials", ["stored_file_id"], unique=False)
    op.create_index(op.f("ix_materials_uploader_id"), "materials", ["uploader_id"], unique=False)
    op.create_index(op.f("ix_materials_processing_status"), "materials", ["processing_status"], unique=False)
    op.create_index(op.f("ix_materials_duplicate_status"), "materials", ["duplicate_status"], unique=False)
    op.create_index("ix_materials_subject_active", "materials", ["subject_id", "deleted_at"], unique=False)

    op.create_table(
        "duplicate_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_material_id", sa.Uuid(), nullable=False),
        sa.Column("matched_material_id", sa.Uuid(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_duplicate_reviews_subject_id_subjects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_material_id"], ["materials.id"], name=op.f("fk_duplicate_reviews_candidate_material_id_materials"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["matched_material_id"], ["materials.id"], name=op.f("fk_duplicate_reviews_matched_material_id_materials"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"], ["profiles.id"], name=op.f("fk_duplicate_reviews_reviewer_id_profiles"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_duplicate_reviews")),
    )
    op.create_index(op.f("ix_duplicate_reviews_subject_id"), "duplicate_reviews", ["subject_id"], unique=False)
    op.create_index(op.f("ix_duplicate_reviews_candidate_material_id"), "duplicate_reviews", ["candidate_material_id"], unique=False)
    op.create_index(op.f("ix_duplicate_reviews_matched_material_id"), "duplicate_reviews", ["matched_material_id"], unique=False)
    op.create_index(op.f("ix_duplicate_reviews_status"), "duplicate_reviews", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_duplicate_reviews_status"), table_name="duplicate_reviews")
    op.drop_index(op.f("ix_duplicate_reviews_matched_material_id"), table_name="duplicate_reviews")
    op.drop_index(op.f("ix_duplicate_reviews_candidate_material_id"), table_name="duplicate_reviews")
    op.drop_index(op.f("ix_duplicate_reviews_subject_id"), table_name="duplicate_reviews")
    op.drop_table("duplicate_reviews")

    op.drop_index("ix_materials_subject_active", table_name="materials")
    op.drop_index(op.f("ix_materials_duplicate_status"), table_name="materials")
    op.drop_index(op.f("ix_materials_processing_status"), table_name="materials")
    op.drop_index(op.f("ix_materials_uploader_id"), table_name="materials")
    op.drop_index(op.f("ix_materials_stored_file_id"), table_name="materials")
    op.drop_index(op.f("ix_materials_subject_id"), table_name="materials")
    op.drop_table("materials")

    op.drop_index(op.f("ix_stored_files_sha256"), table_name="stored_files")
    op.drop_index(op.f("ix_stored_files_uploader_id"), table_name="stored_files")
    op.drop_table("stored_files")
