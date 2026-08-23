import datetime as dt

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class PointsCriterion(Base):
    """The General Skilled Migration points test: what earns how many
    points (age bands, English, work experience, qualifications, ...).

    Standalone reference table — no FK. Sourced from the points-table page
    (`/points-table`, the correct sibling of the catalogued-but-wrong
    `/points-tested` URL), decoded the same hidden-field-JSON way as every
    other Home Affairs page.

    `criterion_name` is not always the page's own criterion label alone:
    "Skilled employment experience" carries two tables (overseas /
    Australian) distinguished only by a preceding heading, so its rows
    carry `"Skilled employment experience — <heading>"` — see
    `extraction/points_criteria.py`.
    """

    __tablename__ = "points_criteria_reference"
    __table_args__ = (
        UniqueConstraint(
            "criterion_name", "band_description",
            name="uq_points_criteria_name_band",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    criterion_name: Mapped[str] = mapped_column(String, nullable=False)
    band_description: Mapped[str] = mapped_column(String, nullable=False)
    points_value: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
