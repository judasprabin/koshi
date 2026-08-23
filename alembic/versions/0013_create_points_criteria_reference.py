"""create points_criteria_reference

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-23

Resolves issue #16 (Phase B). Sourced from the SkillSelect points-table
page, decoded via the same hidden-field-JSON pattern as every other Home
Affairs page. Standalone reference table, no FK.
"""
import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "points_criteria_reference",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("criterion_name", sa.String(), nullable=False),
        sa.Column("band_description", sa.String(), nullable=False),
        sa.Column("points_value", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "criterion_name", "band_description",
            name="uq_points_criteria_name_band",
        ),
    )


def downgrade() -> None:
    op.drop_table("points_criteria_reference")
