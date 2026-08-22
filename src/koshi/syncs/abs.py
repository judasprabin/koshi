import datetime as dt
import logging

import httpx
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_bytes
from koshi.extraction.abs_anzsco import (
    ANZSCO_EDITION as ABS_ANZSCO_EDITION,
    parse_abs_occupations,
)
from koshi.models.occupations import Occupation
from koshi.pipeline import _RowsWithSkipCount
from koshi.sources import ABS_ANZSCO

logger = logging.getLogger(__name__)


def sync_abs_occupations(
    session: Session, *, url: str = ABS_ANZSCO.url, client: httpx.Client | None = None
) -> list[Occupation]:
    """Load the occupation set from the ABS classification (Table 5).

    The JSA listing is a *browse UI*, and it surfaces only 878 of ANZSCO's
    1,076 six-digit occupations. That shortfall is not cosmetic: a live
    invitation round referenced 23 occupations that resolve to perfectly
    valid ANZSCO codes which simply were not in the JSA grid, so their
    rounds could not be linked at all.

    ABS is the classification's custodian, so its Table 5 is the
    authoritative occupation universe. JSA remains synced because it also
    publishes 4-digit unit groups (which NSW's list joins on) and is the
    cadence signal; the two merge by primary key.
    """
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    workbook = fetch_bytes(url, domain="www.abs.gov.au", category="abs_anzsco", client=client)
    result = parse_abs_occupations(workbook)

    written: list[Occupation] = []
    for row in result.rows:
        session.merge(
            Occupation(
                code=row.occupation_code,
                name=row.title,
                unit_group=row.occupation_code[:4],
                code_grain="occupation",
                anzsco_edition=ABS_ANZSCO_EDITION,
                source_url=url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
        written.append(row)
    session.commit()
    logger.info("abs_occupations: merged %d occupations", len(written))
    rows = _RowsWithSkipCount(written)
    rows.skipped = result.skipped
    return rows
