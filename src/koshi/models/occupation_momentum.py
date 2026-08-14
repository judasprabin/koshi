import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class OccupationMomentum(Base):
    __tablename__ = "occupation_momentum"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occupation_code: Mapped[str] = mapped_column(String, ForeignKey("occupations.code"), nullable=False)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)  # rising | falling | steady
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="derived")
