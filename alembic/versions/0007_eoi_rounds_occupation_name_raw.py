"""eoi_rounds: store the occupation name the source actually publishes

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-18

SkillSelect publishes occupation *names* ("Actuary", "Carpenter") and never
ANZSCO codes, so `occupation_code` cannot be populated at extraction time -
it needs the LIN-first name->code crosswalk, which lands separately. Until
then every scraped row has occupation_code = NULL.

That breaks dedup. The existing unique constraint covers
(visa_code, occupation_code, round_date), and Postgres treats NULLs as
distinct, so with occupation_code NULL on every row the constraint stops
preventing anything - a re-run would re-insert all 140 rows and manufacture
fake momentum, which is the exact failure constraint 0006 was added to stop.

So the constraint moves onto occupation_name_raw, which is NOT NULL and is
what the source actually keys on.
"""
import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "eoi_rounds",
        sa.Column("occupation_name_raw", sa.String(), nullable=True),
    )

    # Backfill before the NOT NULL: any pre-existing row keyed on a code
    # keeps a usable natural key rather than being deleted or blocking the
    # migration.
    op.execute(
        "UPDATE eoi_rounds SET occupation_name_raw = occupation_code "
        "WHERE occupation_name_raw IS NULL AND occupation_code IS NOT NULL"
    )
    op.execute(
        "UPDATE eoi_rounds SET occupation_name_raw = '(unknown)' "
        "WHERE occupation_name_raw IS NULL"
    )

    op.alter_column("eoi_rounds", "occupation_name_raw", nullable=False)

    op.drop_constraint(
        "uq_eoi_rounds_visa_occupation_round_date", "eoi_rounds", type_="unique"
    )
    op.create_unique_constraint(
        "uq_eoi_rounds_visa_occupation_name_round_date",
        "eoi_rounds",
        ["visa_code", "occupation_name_raw", "round_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_eoi_rounds_visa_occupation_name_round_date", "eoi_rounds", type_="unique"
    )
    op.create_unique_constraint(
        "uq_eoi_rounds_visa_occupation_round_date",
        "eoi_rounds",
        ["visa_code", "occupation_code", "round_date"],
    )
    op.drop_column("eoi_rounds", "occupation_name_raw")
