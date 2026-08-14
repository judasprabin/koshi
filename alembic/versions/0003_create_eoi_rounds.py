"""create eoi_rounds

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-14
"""
import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eoi_rounds",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("visa_code", sa.String, nullable=False),
        sa.Column("occupation_code", sa.String, sa.ForeignKey("occupations.code"), nullable=True),
        sa.Column("round_date", sa.Date, nullable=False),
        sa.Column("threshold_points", sa.Integer, nullable=False),
        sa.Column("invitations_issued", sa.Integer, nullable=True),
        sa.Column("source_url", sa.String, nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String, nullable=False, server_default="official_scraped"),
    )


def downgrade() -> None:
    op.drop_table("eoi_rounds")
