"""create occupation_titles - the name->code crosswalk

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-18

SkillSelect publishes occupation names and never ANZSCO codes, so
eoi_rounds.occupation_code cannot be populated without a crosswalk.

Two sources are carried because neither is sufficient alone: measured
against a live invitation round's 140 occupations, LIN 19/051 resolves
132/140 and the ABS ANZSCO 2022 workbook resolves 132/140, while their
union resolves 140/140.

No FK to occupations.code: this is a reference mapping that legitimately
names codes koshi's occupation table does not carry (LIN 19/051 is coded
against ANZSCO 2013, 25 of whose codes are absent from 2022; the ABS sheet
is a coder list including non-occupations such as 099960 Retired).
"""
import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "occupation_titles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("title_normalized", sa.String(), nullable=False),
        sa.Column("occupation_code", sa.String(), nullable=False),
        sa.Column("title_source", sa.String(), nullable=False),
        sa.Column("anzsco_edition", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # Not unique on title alone: the same title resolves to different
        # codes across the two sources, and that disagreement is real data.
        sa.UniqueConstraint(
            "title_normalized", "title_source",
            name="uq_occupation_titles_normalized_source",
        ),
        sa.CheckConstraint(
            "title_source IN ('LIN_19_051', 'ABS_ANZSCO')",
            name="ck_occupation_titles_source",
        ),
    )
    op.create_index(
        "ix_occupation_titles_title_normalized",
        "occupation_titles",
        ["title_normalized"],
    )


def downgrade() -> None:
    op.drop_index("ix_occupation_titles_title_normalized", table_name="occupation_titles")
    op.drop_table("occupation_titles")
