import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base

# Resolution order. LIN 19/051 is the binding legislative instrument, so
# where the two sources disagree it wins; ABS is the fallback that covers
# occupations the instrument does not name.
TITLE_SOURCE_PRECEDENCE = ("LIN_19_051", "ABS_ANZSCO")


class OccupationTitle(Base):
    """Occupation title -> ANZSCO code, per source.

    Exists because SkillSelect publishes occupation *names* and never codes,
    so `eoi_rounds.occupation_code` cannot be filled without a crosswalk.

    Deliberately NOT unique on `title` alone: the same title resolves to
    different codes in the two sources (Management Consultant, Plumber
    (General), Statistician), and collapsing that would silently pick one.
    The disagreement is real data and is kept.

    Deliberately has NO foreign key to `occupations.code`. This is a
    reference mapping, and it legitimately names codes koshi's occupation
    table does not carry - LIN 19/051 is coded against ANZSCO 2013 (25 of
    its codes are absent from 2022), and the ABS sheet is a coder list that
    includes non-occupations such as `099960 Retired`. An FK would reject
    valid crosswalk rows.
    """

    __tablename__ = "occupation_titles"
    __table_args__ = (
        UniqueConstraint(
            "title_normalized", "title_source",
            name="uq_occupation_titles_normalized_source",
        ),
        CheckConstraint(
            "title_source IN ('LIN_19_051', 'ABS_ANZSCO')",
            name="ck_occupation_titles_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # As published, preserved verbatim: LIN renders titles in lower case
    # ("construction project manager") and ABS in title case.
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Case- and whitespace-folded form, which is what lookups match on.
    # Stored rather than computed at query time so the unique constraint can
    # enforce one row per (normalized title, source).
    title_normalized: Mapped[str] = mapped_column(String, nullable=False, index=True)
    occupation_code: Mapped[str] = mapped_column(String, nullable=False)
    title_source: Mapped[str] = mapped_column(String, nullable=False)
    anzsco_edition: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(
        String, nullable=False, default="official_scraped"
    )
