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

    # Fix 3: a parse failure must not permanently freeze a source page. The
    # commit of content_hash/last_changed_at in fetch_and_register happens
    # before the caller attempts to parse, so "should I parse" must be
    # decided from this separate watermark, not from fetch_and_register's
    # changed bool alone.
    op.add_column(
        "source_pages",
        sa.Column("last_extracted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Fix 4: reject nonsensical ceiling data at the DB layer, mirroring the
    # seeds/loader.py check — issued can't exceed ceiling, and ceiling
    # can't be zero/negative (the latter also guards against
    # ZeroDivisionError in generate_ceiling_insight).
    op.create_check_constraint(
        "ck_ceiling_usage_issued_within_ceiling",
        "ceiling_usage",
        "issued <= ceiling AND ceiling > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ceiling_usage_issued_within_ceiling", "ceiling_usage", type_="check")
    op.drop_column("source_pages", "last_extracted_at")
    op.drop_constraint("uq_eoi_rounds_visa_occupation_round_date", "eoi_rounds", type_="unique")
