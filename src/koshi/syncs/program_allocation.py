import datetime as dt
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.program_allocation import parse_program_allocation
from koshi.models.program_allocation import ProgramAllocation
from koshi.pipeline import _RowsWithSkipCount, _needs_extraction
from koshi.sources import PROGRAM_ALLOCATION

logger = logging.getLogger(__name__)


def sync_program_allocation(
    session: Session,
    *,
    url: str = PROGRAM_ALLOCATION.url,
    client: httpx.Client | None = None,
) -> list[ProgramAllocation]:
    """Load annual migration program planning levels (data model C15).

    Upserts by (program_year, stream_name): the current-year figure is
    occasionally revised (Budget + mid-year updates), so a re-run should
    update in place rather than duplicate.
    """
    page, _changed, text = fetch_and_register(
        session, url=url, domain="immi.homeaffairs.gov.au",
        category="program_allocation", client=client,
    )
    if not _needs_extraction(page):
        return []

    retrieved_at = dt.datetime.now(dt.timezone.utc)
    result = parse_program_allocation(text)
    if result.skipped:
        logger.warning("program_allocation: skipped %d malformed row(s)", result.skipped)

    written: list[ProgramAllocation] = []
    for row in result.rows:
        existing = session.scalar(
            select(ProgramAllocation).where(
                ProgramAllocation.program_year == row.program_year,
                ProgramAllocation.stream_name == row.stream_name,
            )
        )
        if existing is None:
            record = ProgramAllocation(
                program_year=row.program_year, stream_name=row.stream_name,
                places=row.places, source_url=url, retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
            session.add(record)
            written.append(record)
        elif existing.places != row.places:
            existing.places = row.places
            existing.retrieved_at = retrieved_at
            written.append(existing)

    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    logger.info(
        "program_allocation: %d rows parsed, %d written", len(result.rows), len(written),
    )
    rows = _RowsWithSkipCount(written)
    rows.skipped = result.skipped
    return rows
