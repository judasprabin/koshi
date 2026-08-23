import datetime as dt

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class OccupationListMembership(Base):
    """Current membership of MLTSSL / STSOL / ROL / CSOL, per compilation.

    `list_change_log` (C13) is deliberately not a separately-sourced
    table — it's a *derivative* of this one: diff two `compilation_date`s
    once there are two to diff. With only one compilation loaded so far,
    there's nothing to derive yet.

    CSOL is a valid `list_name` but not yet populated — its source
    (`F2024L01618`) isn't built. The CHECK constraint allows for it
    without claiming coverage that doesn't exist.
    """

    __tablename__ = "occupation_list_membership"
    __table_args__ = (
        CheckConstraint(
            "list_name IN ('MLTSSL', 'STSOL', 'ROL', 'CSOL')",
            name="ck_occupation_list_membership_list_name",
        ),
        UniqueConstraint(
            "list_name", "occupation_code", "compilation_date",
            name="uq_occupation_list_membership_list_code_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    list_name: Mapped[str] = mapped_column(String, nullable=False)
    occupation_code: Mapped[str] = mapped_column(String, ForeignKey("occupations.code"), nullable=False)
    anzsco_edition: Mapped[str] = mapped_column(String, nullable=False)
    compilation_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
