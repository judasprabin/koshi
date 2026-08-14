"""create ceiling_usage

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-14
"""
import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ceiling_usage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("occupation_code", sa.String, sa.ForeignKey("occupations.code"), nullable=False),
        sa.Column("program_year", sa.String, nullable=False),
        sa.Column("issued", sa.Integer, nullable=False),
        sa.Column("ceiling", sa.Integer, nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("source_url", sa.String, nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String, nullable=False, server_default="official_curated"),
    )


def downgrade() -> None:
    op.drop_table("ceiling_usage")
