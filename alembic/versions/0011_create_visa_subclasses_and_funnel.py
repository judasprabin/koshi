"""create visa_subclasses and application_funnel

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-18

Both are populated from BP0068 (data.gov.au, CC-BY 2.5), which supplies
per-subclass, per-program-year grant counts - the field the design had
expected to ship NULL for want of any pathway-level breakdown.

application_funnel.submitted_count is nullable and permanently so: the
audit established EOI submission counts are not published in any form.
invited_count is nullable because it exists at round grain rather than
program year, and approximating across grains would misstate it.

Deliberately NO `granted_count >= 0` check. BP0068 is confidentialised
("masked" in its own filename): small cells are perturbed for privacy, and
one real row - subclass 110 Interdependency, 2019-20 - reports -2. That is
a published figure, so it is stored as published. Clamping it to zero would
be fabricating data to satisfy an assumption the source does not share.
"""
import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visa_subclasses",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("visa_category", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "application_funnel",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("visa_code", sa.String(), nullable=False),
        sa.Column("program_year", sa.String(), nullable=False),
        sa.Column("submitted_count", sa.Integer(), nullable=True),
        sa.Column("invited_count", sa.Integer(), nullable=True),
        sa.Column("granted_count", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["visa_code"], ["visa_subclasses.code"]),
        sa.UniqueConstraint("visa_code", "program_year", name="uq_application_funnel_visa_year"),
    )


def downgrade() -> None:
    op.drop_table("application_funnel")
    op.drop_table("visa_subclasses")
