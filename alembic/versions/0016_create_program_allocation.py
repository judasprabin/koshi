"""create program_allocation

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-23

Resolves issue #17 (Phase B). Corrects the original spec's sourcing
method: docs/superpowers/research/2026-08-16-koshi-source-urls.md found
the planning-levels page needs no PDF/manual curation at all — it's the
same hidden-field JSON every other Home Affairs page uses.
"""
import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "program_allocation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("program_year", sa.String(), nullable=False),
        sa.Column("stream_name", sa.String(), nullable=False),
        sa.Column("places", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_year", "stream_name", name="uq_program_allocation_year_stream"),
    )


def downgrade() -> None:
    op.drop_table("program_allocation")
