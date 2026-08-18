import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class Occupation(Base):
    __tablename__ = "occupations"
    __table_args__ = (
        # Mirrors migration 0008.
        CheckConstraint(
            "code_grain IN ('unit_group', 'occupation')",
            name="ck_occupations_code_grain",
        ),
    )

    code: Mapped[str] = mapped_column(String, primary_key=True)  # ANZSCO code
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit_group: Mapped[str] = mapped_column(String, nullable=False)
    # The JSA listing interleaves 4-digit unit groups (2211 Accountants) with
    # 6-digit occupations (221111 Accountants (General)) in one result set,
    # and koshi's other sources disagree on which width they key by — NSW
    # joins at 4-digit, QLD and LIN 19/051 at 6-digit. Without this marker
    # the two kinds of row are indistinguishable in the table and a join
    # silently matches the wrong grain.
    code_grain: Mapped[str] = mapped_column(String, nullable=False, default="occupation")
    # Which ANZSCO edition this code comes from. Three are simultaneously
    # live across koshi's sources, and they do not fully overlap: LIN
    # 19/051 (the binding instrument) is 2013 and carries codes such as
    # 394111 Cabinetmaker that the 2022 classification does not. Recording
    # the edition lets those coexist instead of looking like bad data.
    anzsco_edition: Mapped[str] = mapped_column(String, nullable=False, default="2022")
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
