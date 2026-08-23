import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class EligibilityRequirement(Base):
    """Prose reference for the three near-static eligibility requirements
    — health, character, and English language.

    Tier 5 (manual YAML curation), like `ceiling_usage`: the three source
    pages are near-static prose, not tabular data, and — unusually for
    koshi's sources — each of the three uses a genuinely different page
    encoding (see seeds/eligibility_requirements_manual.yaml's header
    comment), so there is no single automated parser to write. The seed
    is curated once from the live pages and re-verified periodically,
    not re-fetched on every run.
    """

    __tablename__ = "eligibility_requirements"
    __table_args__ = (
        CheckConstraint(
            "requirement_type IN ('health', 'character', 'english_language')",
            name="ck_eligibility_requirements_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    requirement_type: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_curated")
