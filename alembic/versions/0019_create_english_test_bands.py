"""create english_test_bands

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-24

Resolves issue #19 (Phase C). Two legislative instruments, not the
catalogued (tableless) Home Affairs English page.
"""
import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "english_test_bands",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("test_name", sa.String(), nullable=False),
        sa.Column("band_level", sa.String(), nullable=False),
        sa.Column("score_requirement", sa.String(), nullable=False),
        sa.Column("points_awarded", sa.Integer(), nullable=False),
        sa.Column("cost", sa.String(), nullable=True),
        sa.Column("validity_period", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("test_name", "band_level", name="uq_english_test_bands_test_band"),
    )


def downgrade() -> None:
    op.drop_table("english_test_bands")
