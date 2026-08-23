import datetime as dt

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class VisaSubclass(Base):
    """Visa subclass reference table.

    Seeded from BP0068, which carries 62 subclasses with two structured
    taxonomy fields — Category and Type. (Earlier docs described a full
    five-level Program -> Category -> Type -> Sub-type -> Subclass
    breakdown; the live pivot cache only actually declares Category and
    Type as fields — issue #10 corrected this against the real source
    rather than the aspirational spec.) Note that is 62 subclasses *with
    grants*, so it is a lower bound on the full registry rather than the
    registry itself - the fee API's 150 records are wider. Recorded here
    because it is the only verified structured visa taxonomy koshi has,
    and `application_funnel` needs an FK parent.

    `permanence`, `age_limit`, and other static facts from the original
    target spec are deliberately not columns here: no published structured
    source for them was ever found (audit finding G5, NO SOURCE) — adding
    them would mean shipping permanently-NULL columns with no path to ever
    populate them.
    """

    __tablename__ = "visa_subclasses"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    visa_category: Mapped[str | None] = mapped_column(String, nullable=True)
    # Issue #10: BP0068's pivot cache declares a "Visa Type" field
    # (e.g. "Points-tested", "Employer Sponsored") that was extracted
    # nowhere until this column — the concrete, verified part of widening
    # this table to BP0068's taxonomy. Nullable: BP0068 sometimes reports
    # it as an empty string, and older/edition-only rows never carry it.
    visa_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
