import datetime as dt
import logging

import httpx
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.points_criteria import parse_points_criteria
from koshi.models.points_criteria_reference import PointsCriterion
from koshi.pipeline import _RowsWithSkipCount, _needs_extraction
from koshi.sources import POINTS_CRITERIA
from koshi.syncs._upsert import upsert_by_key

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
        record, was_written = upsert_by_key(
            session, PointsCriterion,
            key={"criterion_name": row.criterion_name, "band_description": row.band_description},
            values={"points_value": row.points_value},
            retrieved_at=retrieved_at,
            build=lambda row=row: PointsCriterion(
                criterion_name=row.criterion_name,
                band_description=row.band_description,
                points_value=row.points_value,
                source_url=url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            ),
        )
        if was_written:
            written.append(record)

    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    logger.info(
        "points_criteria: %d rows parsed, %d written", len(result.rows), len(written),
    )
    rows = _RowsWithSkipCount(written)
    rows.skipped = result.skipped
    return rows
