"""create source_pages

Revision ID: 0001
Revises:
Create Date: 2026-08-14
"""
import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_pages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("url", sa.String, nullable=False, unique=True),
        sa.Column("domain", sa.String, nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("content_hash", sa.String, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="active"),
    )


def downgrade() -> None:
    op.drop_table("source_pages")
