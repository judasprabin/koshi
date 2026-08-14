import datetime as dt

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class SourcePage(Base):
    """The crawl registry — replaces the old research/au-visa-sources +
    Notion pair (design spec §5). Metadata about a page, not a fact: no
    reliability_tier/source_url here, because this table *is* the source."""

    __tablename__ = "source_pages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_checked_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_changed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    # Watermark for the extraction (parsing) step, separate from the fetch
    # step's last_changed_at. fetch_and_register commits content_hash /
    # last_changed_at before the caller ever attempts to parse, so if
    # parsing fails this is left unset (or stale) and the next sync run
    # retries — see pipeline.py's _needs_extraction.
    last_extracted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
