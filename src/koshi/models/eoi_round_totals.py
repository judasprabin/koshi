import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class EoiRoundTotal(Base):
    """SkillSelect's Table A — total EOIs invited per subclass, per round.

    Not derivable from `eoi_rounds`: that table is per-occupation minimum
    score, never a per-subclass round total. Genuinely new data (issue
    #25), not in the original 22-table catalog.

    `visa_code` is nullable: a row whose label doesn't parse to a 3-digit
    subclass code is still stored (not silently dropped), matching how
    `eoi_rounds.occupation_code` stays NULL rather than inventing a guess.
    `visa_label` (the full raw text) is the real identity — different
    streams of the same subclass carry different qualifier text.
    """

    __tablename__ = "eoi_round_totals"
    __table_args__ = (
        UniqueConstraint("visa_label", "round_date", name="uq_eoi_round_totals_label_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    visa_code: Mapped[str | None] = mapped_column(String, ForeignKey("visa_subclasses.code"), nullable=True)
    visa_label: Mapped[str] = mapped_column(String, nullable=False)
    round_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    total_invited: Mapped[int] = mapped_column(Integer, nullable=False)
    # As published ("24/04/2026") rather than parsed to a DATE: format
    # consistency across every round hasn't been verified, and this field
    # is display-only, not joined on.
    tie_break_date: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
