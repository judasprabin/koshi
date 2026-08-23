import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class EoiInvitationMonthly(Base):
    """SkillSelect's Table C — monthly invitation counts per subclass,
    cumulative for the current program year.

    Genuinely new data (issue #25) feeding, in particular, the 5-year
    threshold trend endpoint (Epic 6) — not in the original 22-table
    catalog. Re-syncing an in-progress program year updates its rows in
    place (upsert by visa_label/program_year/month) since later months
    fill in as the year progresses.
    """

    __tablename__ = "eoi_invitation_monthly"
    __table_args__ = (
        UniqueConstraint(
            "visa_label", "program_year", "month",
            name="uq_eoi_invitation_monthly_label_year_month",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    visa_code: Mapped[str | None] = mapped_column(String, ForeignKey("visa_subclasses.code"), nullable=True)
    visa_label: Mapped[str] = mapped_column(String, nullable=False)
    program_year: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "2025-26"
    month: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "Jul", as published
    invited_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
