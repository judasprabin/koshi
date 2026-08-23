import datetime as dt
import logging
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register, fetch_text
from koshi.extraction.skills_priority import discover_spl_data_path, parse_skills_priority_ratings
from koshi.models.occupations import Occupation
from koshi.models.skills_priority_ratings import SkillsPriorityRating
from koshi.pipeline import _RowsWithSkipCount, _needs_extraction
from koshi.sources import SKILLS_PRIORITY

logger = logging.getLogger(__name__)

CODE_GRAIN = "6"
EDITION = "2022"


def sync_skills_priority(
    session: Session,
    *,
    url: str = SKILLS_PRIORITY.url,
    client: httpx.Client | None = None,
) -> list[SkillsPriorityRating]:
    """Load JSA's occupation shortage ratings (data model C18), scoped to
    6-digit ANZSCO 2022 codes and the latest published year — see
    extraction/skills_priority.py's module docstring for the full
    dimension breakdown and what's deliberately deferred.

    Two-step fetch: the page only reveals the current data file's path
    (it's timestamped and changes whenever JSA republishes), so this
    fetches the page first, then the discovered data URL.

    `as_of_date` is derived from fetch time, not a date in the payload —
    the source gives a year per rating, not a specific date, same
    "weakly sourced" treatment as processing_times' as_of_date.
    """
    page, _changed, page_html = fetch_and_register(
        session, url=url, domain="www.jobsandskills.gov.au",
        category="skills_priority", client=client,
    )
    if not _needs_extraction(page):
        return []

    data_path = discover_spl_data_path(page_html)
    data_url = urljoin(url, data_path)
    data_json = fetch_text(
        data_url, domain="www.jobsandskills.gov.au", category="skills_priority_data",
        client=client,
    )

    retrieved_at = dt.datetime.now(dt.timezone.utc)
    as_of_date = retrieved_at.date()
    result = parse_skills_priority_ratings(data_json, code_grain=CODE_GRAIN, edition=EDITION)
    skipped = result.skipped

    written: list[SkillsPriorityRating] = []
    for row in result.rows:
        if session.get(Occupation, row.occupation_code) is None:
            skipped += 1
            continue
        existing = session.scalar(
            select(SkillsPriorityRating).where(
                SkillsPriorityRating.occupation_code == row.occupation_code,
                SkillsPriorityRating.jurisdiction == row.jurisdiction,
                SkillsPriorityRating.as_of_date == as_of_date,
            )
        )
        if existing is None:
            record = SkillsPriorityRating(
                occupation_code=row.occupation_code, jurisdiction=row.jurisdiction,
                shortage_rating=row.shortage_rating,
                future_demand_rating=row.future_demand_rating,
                as_of_date=as_of_date, source_url=data_url, retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
            session.add(record)
            written.append(record)
        elif existing.shortage_rating != row.shortage_rating:
            existing.shortage_rating = row.shortage_rating
            existing.retrieved_at = retrieved_at
            written.append(existing)

    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    logger.info(
        "skills_priority: %d rows parsed, %d written, %d skipped",
        len(result.rows), len(written), skipped,
    )
    rows = _RowsWithSkipCount(written)
    rows.skipped = skipped
    return rows
