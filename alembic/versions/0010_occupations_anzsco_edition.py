"""occupations: record which ANZSCO edition a row came from

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-18

Three ANZSCO editions are simultaneously live in koshi's sources:

    F2024L01616 (pins migration)  ANZSCO 2013
    LIN 19/051 (binding list)     ANZSCO 2013
    F2024L01618 (CSOL)            ANZSCO 2022
    JSA / ABS                     ANZSCO 2022 (and OSCA alongside)

That is not bookkeeping. A live invitation round invites `Cabinetmaker`,
which LIN 19/051 carries as 394111 under the 2013 edition and which the
2022 classification does not contain at all. Without an edition column
such a row looks like bad data rather than a different vocabulary, and
the occupation cannot be linked.

`code` stays the primary key rather than moving to (code, edition): it
anchors seven foreign keys, and the editions overwhelmingly agree. The
column records provenance of the code space and lets edition-only codes
coexist, which is what unblocks the affected rounds.
"""
import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("occupations", sa.Column("anzsco_edition", sa.String(), nullable=True))
    # Everything loaded before this column existed came from the JSA/ABS
    # 2022 sources.
    op.execute("UPDATE occupations SET anzsco_edition = '2022' WHERE anzsco_edition IS NULL")
    op.alter_column("occupations", "anzsco_edition", nullable=False)


def downgrade() -> None:
    op.drop_column("occupations", "anzsco_edition")
