import datetime as dt
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.points_criteria import parse_points_criteria
from koshi.models.points_criteria_reference import PointsCriterion
from koshi.pipeline import _RowsWithSkipCount, _needs_extraction
from koshi.sources import POINTS_CRITERIA

logger = logging.getLogger(__name__)


def sync_points_criteria(
    session: Session,
    *,
    url: str = POINTS_CRITERIA.url,
    client: httpx.Client | None = None,
) -> list[PointsCriterion]:
    """Load the General Skilled Migration points-test criteria.

    Upserts by (criterion_name, band_description): the points test changes
    only on major policy reform, so a re-run should update an existing
    band's points_value in place rather than duplicate it.
    """
    page, _changed, text = fetch_and_register(
        session, url=url, domain="immi.homeaffairs.gov.au",
        category="points_criteria", client=client,
    )
    if not _needs_extraction(page):
        return []

    retrieved_at = dt.datetime.now(dt.timezone.utc)
    result = parse_points_criteria(text)
    if result.skipped:
        logger.warning("points_criteria: skipped %d malformed row(s)", result.skipped)

    written: list[PointsCriterion] = []
    for row in result.rows:
        existing = session.scalar(
            select(PointsCriterion).where(
                PointsCriterion.criterion_name == row.criterion_name,
                PointsCriterion.band_description == row.band_description,
            )
        )
        if existing is None:
            record = PointsCriterion(
                criterion_name=row.criterion_name,
                band_description=row.band_description,
                points_value=row.points_value,
                source_url=url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
            session.add(record)
            written.append(record)
        elif existing.points_value != row.points_value:
            existing.points_value = row.points_value
            existing.retrieved_at = retrieved_at
            written.append(existing)

    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    logger.info(
        "points_criteria: %d rows parsed, %d written", len(result.rows), len(written),
    )
    rows = _RowsWithSkipCount(written)
    rows.skipped = result.skipped
    return rows
