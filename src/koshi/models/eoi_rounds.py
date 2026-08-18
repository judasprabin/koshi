import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class EoiRound(Base):
    __tablename__ = "eoi_rounds"
    __table_args__ = (
        # Mirrors migration 0007: one row per (visa_code,
        # occupation_name_raw, round_date) — a whole-page hash change must
        # not be able to re-insert the same round and manufacture fake
        # momentum. Declared here too so Base.metadata (what
        # tests/conftest.py's create_all and Alembic autogenerate both
        # compare against) doesn't drift from what the migration chain
        # actually creates.
        #
        # Keyed on the *name*, not the code: SkillSelect publishes names
        # only, so occupation_code is NULL on every scraped row until the
        # crosswalk resolves it — and Postgres treats NULLs as distinct,
        # which would silently disable dedup entirely.
        UniqueConstraint(
            "visa_code", "occupation_name_raw", "round_date",
            name="uq_eoi_rounds_visa_occupation_name_round_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    visa_code: Mapped[str] = mapped_column(String, nullable=False)
    # What the source actually published, preserved verbatim. Keeping it
    # makes a crosswalk miss visible and re-resolvable later, rather than
    # discarding the only identifier the page gave us.
    occupation_name_raw: Mapped[str] = mapped_column(String, nullable=False)
    # Resolved from occupation_name_raw via the name->code crosswalk, which
    # is not built yet — NULL on every scraped row for now.
    occupation_code: Mapped[str | None] = mapped_column(
        String, ForeignKey("occupations.code"), nullable=True
    )
    round_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    threshold_points: Mapped[int] = mapped_column(Integer, nullable=False)
    invitations_issued: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
