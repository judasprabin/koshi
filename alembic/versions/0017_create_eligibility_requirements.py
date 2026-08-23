"""create eligibility_requirements

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-23

Resolves issue #18. Tier 5 manual curation — see
seeds/eligibility_requirements_manual.yaml's header comment for why
(each of the three source pages uses a different encoding, and none
carry tabular data, so there's no automated parser to write).
"""
import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eligibility_requirements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("requirement_type", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("requirement_type", name="eligibility_requirements_requirement_type_key"),
        sa.CheckConstraint(
            "requirement_type IN ('health', 'character', 'english_language')",
            name="ck_eligibility_requirements_type",
        ),
    )


def downgrade() -> None:
    op.drop_table("eligibility_requirements")
