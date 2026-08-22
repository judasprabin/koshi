import datetime as dt
import logging

import httpx
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register, fetch_text
from koshi.extraction.anzsco_occupations import (
    ParseResult,
    has_next_page,
    parse_anzsco_occupations,
)
from koshi.models.occupations import Occupation
from koshi.pipeline import _RowsWithSkipCount, _needs_extraction
from koshi.resilience import Throttler
from koshi.sources import ANZSCO_OCCUPATIONS

logger = logging.getLogger(__name__)

# The live listing is 103 pages (1,236 results at 12 per page). The cap sits
# above that as a runaway guard; it is not a deliberate truncation.
ANZSCO_MAX_PAGES = 150
# Politeness between sequential requests to a single government host. This
# is the first koshi run that fetches many pages from one domain, and the
# reason resilience.Throttler exists.
ANZSCO_PAGE_INTERVAL_SECONDS = 1.0


def sync_anzsco_occupations(
    session: Session,
    *,
    url: str = ANZSCO_OCCUPATIONS.url,
    client: httpx.Client | None = None,
    max_pages: int = ANZSCO_MAX_PAGES,
) -> list[Occupation]:
    page, _changed, text = fetch_and_register(
        session, url=url, domain="www.jobsandskills.gov.au", category="anzsco_occupations", client=client
    )
    if not _needs_extraction(page):
        return []

    retrieved_at = dt.datetime.now(dt.timezone.utc)
    result = parse_anzsco_occupations(text, source_url=url, retrieved_at=retrieved_at)
    rows = list(result.rows)
    skipped = result.skipped

    # The listing paginates at 12 cards over 103 pages: without following
    # the pager koshi loads 12 of 1,236 occupations. Only page 1 is
    # registered in source_pages — the pages change together, so 103
    # registry rows would add no signal.
    #
    # max_pages is a guard against a pager loop, not a policy choice: it is
    # set above the real page count, so hitting it means the page changed
    # shape and is worth a warning.
    throttle = Throttler(ANZSCO_PAGE_INTERVAL_SECONDS)
    current = 0
    while has_next_page(text, current_page=current) and current + 1 < max_pages:
        current += 1
        throttle.wait()
        page_url = f"{url}?page={current}"
        text = fetch_text(
            page_url,
            domain="www.jobsandskills.gov.au",
            category="anzsco_occupations",
            client=client,
        )
        page_result = parse_anzsco_occupations(
            text, source_url=page_url, retrieved_at=retrieved_at
        )
        rows.extend(page_result.rows)
        skipped += page_result.skipped
    else:
        if current + 1 >= max_pages and has_next_page(text, current_page=current):
            logger.warning(
                "anzsco_occupations: stopped at the %d-page cap with more pages "
                "advertised — the pager may have changed shape",
                max_pages,
            )

    result = ParseResult(rows=rows, skipped=skipped)
    if result.skipped:
        logger.warning("anzsco_occupations: skipped %d malformed row(s)", result.skipped)
    logger.info(
        "anzsco_occupations: parsed %d occupations across %d page(s)",
        len(result.rows), current + 1,
    )
    for occupation in result.rows:
        session.merge(occupation)
    # Only advance the extraction watermark once parsing AND persisting
    # have both succeeded — if parse_anzsco_occupations raised above, this
    # line (and the commit) never runs, so the next sync retries.
    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    rows = _RowsWithSkipCount(result.rows)
    rows.skipped = result.skipped
    return rows
