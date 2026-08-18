import datetime as dt

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class VisaSubclass(Base):
    """Visa subclass reference table.

    Seeded from BP0068, which carries 62 subclasses with a Program ->
    Category -> Type -> Sub-type -> Subclass taxonomy. Note that is 62
    subclasses *with grants*, so it is a lower bound on the full registry
    rather than the registry itself - the fee API's 150 records are wider.
    Recorded here because it is the only verified structured visa taxonomy
    koshi has, and `application_funnel` needs an FK parent.
    """

    __tablename__ = "visa_subclasses"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    visa_category: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
