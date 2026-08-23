"""create eoi_round_totals, eoi_invitation_monthly, eoi_state_nominations

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-23

Resolves issue #25 ("free win" — wiring up already-decoded SkillSelect
Tables A/C/D). None of these three fit any table in the 22-table catalog;
confirmed against the live page rather than assumed. All three key on
visa_label (the full raw text), not visa_code alone: different streams of
the same 3-digit subclass carry different qualifier text across tables
(e.g. subclass 491 is "Family Sponsored" in one table, "State and
Territory Nominated" in another), so visa_code alone would silently
collapse two different things.
"""
import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eoi_round_totals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("visa_code", sa.String(), nullable=True),
        sa.Column("visa_label", sa.String(), nullable=False),
        sa.Column("round_date", sa.Date(), nullable=False),
        sa.Column("total_invited", sa.Integer(), nullable=False),
        sa.Column("tie_break_date", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["visa_code"], ["visa_subclasses.code"]),
        sa.UniqueConstraint("visa_label", "round_date", name="uq_eoi_round_totals_label_date"),
    )
    op.create_table(
        "eoi_invitation_monthly",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("visa_code", sa.String(), nullable=True),
        sa.Column("visa_label", sa.String(), nullable=False),
        sa.Column("program_year", sa.String(), nullable=False),
        sa.Column("month", sa.String(), nullable=False),
        sa.Column("invited_count", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["visa_code"], ["visa_subclasses.code"]),
        sa.UniqueConstraint(
            "visa_label", "program_year", "month",
            name="uq_eoi_invitation_monthly_label_year_month",
        ),
    )
    op.create_table(
        "eoi_state_nominations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("visa_code", sa.String(), nullable=True),
        sa.Column("visa_label", sa.String(), nullable=False),
        sa.Column("state_code", sa.String(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("nominated_count", sa.Integer(), nullable=True),
        sa.Column("suppressed", sa.Boolean(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["visa_code"], ["visa_subclasses.code"]),
        sa.UniqueConstraint(
            "visa_label", "state_code", "period_start", "period_end",
            name="uq_eoi_state_nominations_label_state_period",
        ),
    )


def downgrade() -> None:
    op.drop_table("eoi_state_nominations")
    op.drop_table("eoi_invitation_monthly")
    op.drop_table("eoi_round_totals")
