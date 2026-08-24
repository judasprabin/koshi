"""create skills_priority_ratings

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-23

Resolves issue #22 (Phase C). Widened beyond the original spec to include
jurisdiction — see the model's docstring for why (the audit's "M/R split
is itself geographic" finding, confirmed live: Beef Cattle Farmer rates
NT=S while every other jurisdiction reads NS).
"""
import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skills_priority_ratings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("occupation_code", sa.String(), nullable=False),
        sa.Column("jurisdiction", sa.String(), nullable=False),
        sa.Column("shortage_rating", sa.String(), nullable=False),
        sa.Column("future_demand_rating", sa.String(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["occupation_code"], ["occupations.code"]),
        sa.CheckConstraint(
            "jurisdiction IN ('NAT', 'NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'ACT')",
            name="ck_skills_priority_ratings_jurisdiction",
        ),
        sa.CheckConstraint(
            "shortage_rating IN ('S', 'M', 'R', 'NS')",
            name="ck_skills_priority_ratings_shortage",
        ),
        sa.UniqueConstraint(
            "occupation_code", "jurisdiction", "as_of_date",
            name="uq_skills_priority_ratings_code_jurisdiction_date",
        ),
    )


def downgrade() -> None:
    op.drop_table("skills_priority_ratings")
