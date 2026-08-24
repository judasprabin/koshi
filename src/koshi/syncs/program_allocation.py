import datetime as dt
import logging

import httpx
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.program_allocation import parse_program_allocation
from koshi.models.program_allocation import ProgramAllocation
from koshi.pipeline import _RowsWithSkipCount, _needs_extraction
from koshi.sources import PROGRAM_ALLOCATION
from koshi.syncs._upsert import upsert_by_key

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
        record, was_written = upsert_by_key(
            session, ProgramAllocation,
            key={"program_year": row.program_year, "stream_name": row.stream_name},
            values={"places": row.places},
            retrieved_at=retrieved_at,
            build=lambda row=row: ProgramAllocation(
                program_year=row.program_year, stream_name=row.stream_name,
                places=row.places, source_url=url, retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            ),
        )
        if was_written:
            written.append(record)

    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    logger.info(
        "program_allocation: %d rows parsed, %d written", len(result.rows), len(written),
    )
    rows = _RowsWithSkipCount(written)
    rows.skipped = result.skipped
    return rows
