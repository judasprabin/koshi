"""create occupations

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-14
"""
import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "occupations",
        sa.Column("code", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("unit_group", sa.String, nullable=False),
        sa.Column("source_url", sa.String, nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String, nullable=False, server_default="official_scraped"),
    )


def downgrade() -> None:
    op.drop_table("occupations")
