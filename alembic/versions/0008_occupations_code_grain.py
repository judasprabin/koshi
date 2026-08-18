"""occupations: record whether a code is a unit group or an occupation

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-18

The JSA listing interleaves 4-digit unit-group codes (2211 Accountants)
with 6-digit occupation codes (221111 Accountants (General)) in the same
result set. koshi's other sources disagree about which width they key by:
NSW joins at 4-digit, QLD and LIN 19/051 at 6-digit, JSA mixes both.

Without an explicit grain the two kinds of row are indistinguishable once
loaded - `unit_group` equals `code` for a 4-digit row, which reads as
ordinary data rather than as a different kind of key - and a join against a
source using the other width matches nothing while looking healthy.
"""
import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("occupations", sa.Column("code_grain", sa.String(), nullable=True))

    # Backfill from the code width itself - the only information available
    # for rows loaded before this column existed.
    op.execute(
        "UPDATE occupations SET code_grain = "
        "CASE WHEN length(code) = 4 THEN 'unit_group' ELSE 'occupation' END "
        "WHERE code_grain IS NULL"
    )

    op.alter_column("occupations", "code_grain", nullable=False)
    op.create_check_constraint(
        "ck_occupations_code_grain",
        "occupations",
        "code_grain IN ('unit_group', 'occupation')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_occupations_code_grain", "occupations", type_="check")
    op.drop_column("occupations", "code_grain")
