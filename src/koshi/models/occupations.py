import datetime as dt

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class Occupation(Base):
    __tablename__ = "occupations"

    code: Mapped[str] = mapped_column(String, primary_key=True)  # ANZSCO code
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit_group: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
