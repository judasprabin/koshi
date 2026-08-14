"""create occupation_momentum

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-14
"""
import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "occupation_momentum",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("occupation_code", sa.String, sa.ForeignKey("occupations.code"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String, nullable=False),
        sa.Column("reliability_tier", sa.String, nullable=False, server_default="derived"),
    )


def downgrade() -> None:
    op.drop_table("occupation_momentum")
