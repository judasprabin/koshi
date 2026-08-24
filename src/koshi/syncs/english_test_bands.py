import datetime as dt
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.english_test_bands import (
    parse_functional_english_bands,
    parse_schedule2_bands,
)
from koshi.models.english_test_bands import EnglishTestBand
from koshi.pipeline import _RowsWithSkipCount, _needs_extraction
from koshi.sources import FUNCTIONAL_ENGLISH, LIN25016_SCHEDULE2

logger = logging.getLogger(__name__)


def sync_english_test_bands(
    session: Session,
    *,
    schedule2_url: str = LIN25016_SCHEDULE2.url,
    functional_url: str = FUNCTIONAL_ENGLISH.url,
    client: httpx.Client | None = None,
) -> list[EnglishTestBand]:
    """Load English test score bands from both legislative instruments.

    Two independent fetches (genuinely two different documents, unlike
    skillselect_summary's shared-page case), each gated on its own
    SourcePage watermark. A failure fetching one must not prevent the
    other's rows from loading — the two instruments' bands never
    overlap (Schedule 2 covers Vocational/Competent/Proficient/Superior,
    F2025L00904 covers only Functional), so partial success is a
    coherent, useful state, not a half-broken one.
    """
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    all_rows = []
    skipped = 0

    schedule2_page, _changed, schedule2_text = fetch_and_register(
        session, url=schedule2_url, domain="www.legislation.gov.au",
        category="lin25016_schedule2", client=client,
    )
    if _needs_extraction(schedule2_page):
        result = parse_schedule2_bands(schedule2_text)
        skipped += result.skipped
        all_rows += _persist(session, result.rows, schedule2_url, retrieved_at)
        schedule2_page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
        session.commit()

    functional_page, _changed, functional_text = fetch_and_register(
        session, url=functional_url, domain="www.legislation.gov.au",
        category="functional_english", client=client,
    )
    if _needs_extraction(functional_page):
        result = parse_functional_english_bands(functional_text)
        skipped += result.skipped
        all_rows += _persist(session, result.rows, functional_url, retrieved_at)
        functional_page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
        session.commit()

    logger.info("english_test_bands: %d rows written, %d skipped", len(all_rows), skipped)
    rows = _RowsWithSkipCount(all_rows)
    rows.skipped = skipped
    return rows


def _persist(session: Session, parsed_rows, url: str, retrieved_at) -> list[EnglishTestBand]:
    written: list[EnglishTestBand] = []
    for row in parsed_rows:
        existing = session.scalar(
            select(EnglishTestBand).where(
                EnglishTestBand.test_name == row.test_name,
                EnglishTestBand.band_level == row.band_level,
            )
        )
        if existing is None:
            record = EnglishTestBand(
                test_name=row.test_name, band_level=row.band_level,
                score_requirement=row.score_requirement,
                points_awarded=row.points_awarded,
                source_url=url, retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
            session.add(record)
            written.append(record)
        elif (existing.score_requirement, existing.points_awarded) != (
            row.score_requirement, row.points_awarded,
        ):
            existing.score_requirement = row.score_requirement
            existing.points_awarded = row.points_awarded
            existing.retrieved_at = retrieved_at
            written.append(existing)
    return written
