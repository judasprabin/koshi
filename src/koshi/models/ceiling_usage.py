import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class CeilingUsage(Base):
    __tablename__ = "ceiling_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occupation_code: Mapped[str] = mapped_column(String, ForeignKey("occupations.code"), nullable=False)
    program_year: Mapped[str] = mapped_column(String, nullable=False)
    issued: Mapped[int] = mapped_column(Integer, nullable=False)
    ceiling: Mapped[int] = mapped_column(Integer, nullable=False)
    as_of_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_curated")
