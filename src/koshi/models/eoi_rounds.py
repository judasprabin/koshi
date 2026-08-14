import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class EoiRound(Base):
    __tablename__ = "eoi_rounds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    visa_code: Mapped[str] = mapped_column(String, nullable=False)
    occupation_code: Mapped[str | None] = mapped_column(
        String, ForeignKey("occupations.code"), nullable=True
    )
    round_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    threshold_points: Mapped[int] = mapped_column(Integer, nullable=False)
    invitations_issued: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
