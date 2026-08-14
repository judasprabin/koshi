import datetime as dt

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class CeilingUsage(Base):
    __tablename__ = "ceiling_usage"
    __table_args__ = (
        # Mirrors migration 0006: issued can't exceed ceiling, and ceiling
        # can't be zero/negative (mirrored again by seeds/loader.py's own
        # check, which fails fast before this constraint would even be hit).
        # Declared here too so Base.metadata doesn't drift from what the
        # migration chain actually creates — see tests/test_alembic_migrations.py.
        CheckConstraint(
            "issued <= ceiling AND ceiling > 0",
            name="ck_ceiling_usage_issued_within_ceiling",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occupation_code: Mapped[str] = mapped_column(String, ForeignKey("occupations.code"), nullable=False)
    program_year: Mapped[str] = mapped_column(String, nullable=False)
    issued: Mapped[int] = mapped_column(Integer, nullable=False)
    ceiling: Mapped[int] = mapped_column(Integer, nullable=False)
    as_of_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_curated")
