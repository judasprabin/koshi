import datetime as dt

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class ProgramAllocation(Base):
    """Annual migration program planning levels — places allocated per
    stream, per program year.

    Standalone aggregate table, no FK: streams here (e.g. "Skilled
    Independent", "Employer-Sponsored") are categories, not individual
    visa subclasses, and don't map 1:1 onto visa_subclasses.code.

    Sourced from a hidden-field JSON page, not the PDF the original spec
    assumed — see extraction/program_allocation.py's module docstring.
    """

    __tablename__ = "program_allocation"
    __table_args__ = (
        UniqueConstraint("program_year", "stream_name", name="uq_program_allocation_year_stream"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    program_year: Mapped[str] = mapped_column(String, nullable=False)
    stream_name: Mapped[str] = mapped_column(String, nullable=False)
    places: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
