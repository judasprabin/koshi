"""dedup eoi_rounds; add source_pages extraction watermark; ceiling_usage sanity check

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-15
"""
import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fix 2: a whole-page hash change (build stamp, "last reviewed" date)
    # must not be able to re-insert the same round and manufacture fake
    # momentum — one row per (visa_code, occupation_code, round_date).
    op.create_unique_constraint(
        "uq_eoi_rounds_visa_occupation_round_date",
        "eoi_rounds",
        ["visa_code", "occupation_code", "round_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_eoi_rounds_visa_occupation_round_date", "eoi_rounds", type_="unique")
