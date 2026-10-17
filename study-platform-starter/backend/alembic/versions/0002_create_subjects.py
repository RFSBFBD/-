"""create subjects and subject_members

Revision ID: 0002_create_subjects
Revises: 0001_create_profiles
Create Date: 2026-10-13

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_create_subjects"
down_revision: str | None = "0001_create_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"], ["profiles.id"], name=op.f("fk_subjects_created_by_profiles"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subjects")),
    )
    op.create_index(op.f("ix_subjects_created_by"), "subjects", ["created_by"], unique=False)
    op.create_index(
        "uq_subjects_owner_normalized_active",
        "subjects",
        ["created_by", "normalized_name"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
        sqlite_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "subject_members",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_subject_members_subject_id_subjects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"], name=op.f("fk_subject_members_user_id_profiles"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("subject_id", "user_id", name=op.f("pk_subject_members")),
    )


def downgrade() -> None:
    op.drop_table("subject_members")
    op.drop_index("uq_subjects_owner_normalized_active", table_name="subjects")
    op.drop_index(op.f("ix_subjects_created_by"), table_name="subjects")
    op.drop_table("subjects")
