import datetime as dt

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class SkillsPriorityRating(Base):
    """Jobs and Skills Australia's occupation shortage rating, per
    jurisdiction.

    Widened beyond the original C18 spec's (occupation_code, as_of_date)
    key: the live source rates each occupation independently per
    jurisdiction (national + 8 states/territories), and those ratings
    genuinely differ ("the M/R split is itself geographic" — audit
    finding F7/G11). A key without `jurisdiction` would silently collide
    those into one row.

    Scoped to 6-digit ANZSCO 2022 codes (koshi's primary occupation
    grain) and the latest published year only. The source also carries
    4-digit unit-group codes, the 2024/OSCA edition, and a 2021-onward
    time series — deliberately deferred, the edition split to the same
    ANZSCO->OSCA migration trigger already tracked as issue #13.

    `future_demand_rating` is nullable and, per the audit, always NULL in
    practice — JSA's `d` field has no source (NO SOURCE, not built out).
    """

    __tablename__ = "skills_priority_ratings"
    __table_args__ = (
        CheckConstraint(
            "jurisdiction IN ('NAT', 'NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'ACT')",
            name="ck_skills_priority_ratings_jurisdiction",
        ),
        CheckConstraint(
            "shortage_rating IN ('S', 'M', 'R', 'NS')",
            name="ck_skills_priority_ratings_shortage",
        ),
        UniqueConstraint(
            "occupation_code", "jurisdiction", "as_of_date",
            name="uq_skills_priority_ratings_code_jurisdiction_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occupation_code: Mapped[str] = mapped_column(String, ForeignKey("occupations.code"), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String, nullable=False)
    shortage_rating: Mapped[str] = mapped_column(String, nullable=False)
    future_demand_rating: Mapped[str | None] = mapped_column(String, nullable=True)
    as_of_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
