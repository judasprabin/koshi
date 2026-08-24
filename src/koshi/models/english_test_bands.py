import datetime as dt

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class EnglishTestBand(Base):
    """English language test score bands and their migration points.

    Standalone reference table, no FK. Sourced from two legislative
    instruments (LIN 25/016 Schedule 2 for Vocational/Competent/
    Proficient/Superior, F2025L00904 for Functional English) — the
    catalogued Home Affairs English page has zero tables and cannot
    supply this. See extraction/english_test_bands.py's module docstring
    for the parsing detail (rowspan-flattening, per-skill combination).
    """

    __tablename__ = "english_test_bands"
    __table_args__ = (
        UniqueConstraint("test_name", "band_level", name="uq_english_test_bands_test_band"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    test_name: Mapped[str] = mapped_column(String, nullable=False)
    band_level: Mapped[str] = mapped_column(String, nullable=False)
    score_requirement: Mapped[str] = mapped_column(String, nullable=False)
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    cost: Mapped[str | None] = mapped_column(String, nullable=True)
    validity_period: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
