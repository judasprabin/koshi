import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class ApplicationFunnel(Base):
    """Applications through the pipeline, per visa subclass and program year.

    Only `granted_count` is populated today, from BP0068.

    `submitted_count` is **permanently unavailable**: the 2026-08-17 audit
    searched the decoded SkillSelect page for `submitted`, `lodged`,
    `EOIs on hand`, `EOIs in the system` and `pool` with zero matches, and
    none of Home Affairs' 12 data.gov.au datasets is a SkillSelect/EOI
    dataset. It is nullable and recorded as unavailable, not pending.

    `invited_count` is available but at round/subclass grain rather than
    program year, so it is left for a later reconciliation rather than
    approximated here.

    `granted_count` carries no non-negative check. BP0068 is
    confidentialised - small cells are perturbed for privacy - and one real
    row (subclass 110 Interdependency, 2019-20) reports -2. It is stored as
    published rather than clamped.

    Deviation from the data model's C16: that specifies a second provenance
    trio scoped to `granted_count`, on the assumption that submitted and
    invited would come from a different source on the same row. Since only
    granted is sourced, a single trio describes the row honestly; a second
    can be added when invited_count lands.
    """

    __tablename__ = "application_funnel"
    __table_args__ = (
        UniqueConstraint("visa_code", "program_year", name="uq_application_funnel_visa_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    visa_code: Mapped[str] = mapped_column(String, ForeignKey("visa_subclasses.code"), nullable=False)
    program_year: Mapped[str] = mapped_column(String, nullable=False)
    submitted_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invited_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    granted_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
