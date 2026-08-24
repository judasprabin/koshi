import datetime as dt
import logging

import httpx
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_bytes
from koshi.extraction.bp0068 import parse_bp0068_grants
from koshi.models.application_funnel import ApplicationFunnel
from koshi.models.visa_subclasses import VisaSubclass
from koshi.pipeline import _RowsWithSkipCount
from koshi.sources import BP0068
from koshi.syncs._upsert import upsert_by_key

logger = logging.getLogger(__name__)


def sync_bp0068_grants(
    session: Session, *, url: str = BP0068.url, client: httpx.Client | None = None
) -> list[ApplicationFunnel]:
    """Load per-subclass, per-year grant counts from BP0068.

    Populates `application_funnel.granted_count`, which the design had
    expected to ship NULL. Also seeds `visa_subclasses`, which the funnel
    needs as an FK parent and which nothing else in koshi supplied.

    Upserts by (visa_code, program_year): the dataset is republished
    annually with prior years restated, so a re-run must update rather than
    duplicate.
    """
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    workbook = fetch_bytes(url, domain="data.gov.au", category="bp0068", client=client)
    result = parse_bp0068_grants(workbook)

    for code, name, category, visa_type in sorted(
        {(r.visa_code, r.visa_name, r.visa_category, r.visa_type) for r in result.rows}
    ):
        session.merge(
            VisaSubclass(
                code=code, name=name, visa_category=category,
                visa_type=visa_type or None,
                source_url=url, retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
    session.flush()  # subclasses must exist before the funnel's FK is checked

    written: list[ApplicationFunnel] = []
    for row in result.rows:
        record, was_written = upsert_by_key(
            session, ApplicationFunnel,
            key={"visa_code": row.visa_code, "program_year": row.program_year},
            values={"granted_count": row.granted_count},
            retrieved_at=retrieved_at,
            build=lambda row=row: ApplicationFunnel(
                visa_code=row.visa_code,
                program_year=row.program_year,
                granted_count=row.granted_count,
                source_url=url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            ),
        )
        if was_written:
            written.append(record)
    session.commit()
    logger.info(
        "bp0068: %d records -> %d funnel rows (%d written)",
        result.record_count, len(result.rows), len(written),
    )
    rows = _RowsWithSkipCount(written)
    rows.skipped = result.skipped
    return rows
