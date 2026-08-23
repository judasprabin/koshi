"""create occupation_list_membership

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-23

Resolves issue #21 (occupation_list_membership half only — list_change_log
is deliberately not built: docs/superpowers/research/2026-08-16-koshi-data-model.md
C20 documents it as a *derivative* of this table, diffed across
compilation_date once there are two compilations to diff).
"""
import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "occupation_list_membership",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("list_name", sa.String(), nullable=False),
        sa.Column("occupation_code", sa.String(), nullable=False),
        sa.Column("anzsco_edition", sa.String(), nullable=False),
        sa.Column("compilation_date", sa.Date(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["occupation_code"], ["occupations.code"]),
        sa.CheckConstraint(
            "list_name IN ('MLTSSL', 'STSOL', 'ROL', 'CSOL')",
            name="ck_occupation_list_membership_list_name",
        ),
        sa.UniqueConstraint(
            "list_name", "occupation_code", "compilation_date",
            name="uq_occupation_list_membership_list_code_date",
        ),
    )


def downgrade() -> None:
    op.drop_table("occupation_list_membership")
