"""widen visa_subclasses: add visa_type

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-23

Resolves issue #10. BP0068's pivot cache declares a "Visa Type" field
(e.g. "Points-tested", "Employer Sponsored") alongside "Visa Category",
but the parser only ever extracted Category. This is the concrete,
verified part of "widen visa_subclasses to BP0068's taxonomy" — the
originally-envisioned full five-level Program -> Category -> Type ->
Sub-type -> Subclass breakdown does not exist in the source; only
Category and Type are real structured pivot-cache fields.

Deliberately NOT adding `permanence`, `age_limit`, or other static facts
from the original target spec: audit finding G5 found no published
structured source for them (NO SOURCE) — see the model's docstring.
"""
import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visa_subclasses",
        sa.Column("visa_type", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("visa_subclasses", "visa_type")
