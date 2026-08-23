import datetime as dt

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class EoiStateNomination(Base):
    """SkillSelect's Table D — EOIs that received state/territory
    nomination, per subclass per state, for an explicit reporting period.

    Genuinely new data (issue #25), and a different grain from
    `state_nomination_status` (C12, target: per-occupation open/limited/
    closed status) — this is a nomination *count*, per subclass not
    per occupation, so it does not feed C12 despite the thematic overlap.

    Home Affairs privacy-suppresses small cells ("<5") the same way
    BP0068 masks small grant counts. Stored as `nominated_count=NULL,
    suppressed=True` — a real published fact ("fewer than 5"), not a
    parse failure and not guessed at as a specific number.
    """

    __tablename__ = "eoi_state_nominations"
    __table_args__ = (
        UniqueConstraint(
            "visa_label", "state_code", "period_start", "period_end",
            name="uq_eoi_state_nominations_label_state_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    visa_code: Mapped[str | None] = mapped_column(String, ForeignKey("visa_subclasses.code"), nullable=True)
    visa_label: Mapped[str] = mapped_column(String, nullable=False)
    state_code: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "NSW", "ACT"
    period_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[dt.date] = mapped_column(Date, nullable=False)
    nominated_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
