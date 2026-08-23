import datetime as dt
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.skillselect_summary import parse_skillselect_summary
from koshi.models.eoi_invitation_monthly import EoiInvitationMonthly
from koshi.models.eoi_round_totals import EoiRoundTotal
from koshi.models.eoi_state_nominations import EoiStateNomination
from koshi.pipeline import _RowsWithSkipCount
from koshi.sources import SKILLSELECT_ROUNDS

logger = logging.getLogger(__name__)


def sync_skillselect_summary(
    session: Session,
    *,
    url: str = SKILLSELECT_ROUNDS.url,
    client: httpx.Client | None = None,
) -> list:
    """Load SkillSelect's Tables A/C/D — round totals, the monthly
    invitation matrix, and state/territory nominations (issue #25).

    Deliberately NOT gated on `_needs_extraction`. This shares its URL —
    and therefore its `SourcePage` row and `last_extracted_at` watermark —
    with `sync_skillselect_rounds`, which runs first in `__main__.py`'s
    step list and advances that watermark for Table B's extraction. If
    this function gated on the same watermark, it would see it already
    advanced and skip on every run, including the very first. The parse
    is cheap (one page, no pagination) and every target table upserts
    idempotently by its own unique key, so always parsing here is correct
    and simpler than introducing a second watermark field just to avoid a
    fetch that's already happening anyway.
    """
    _page, _changed, text = fetch_and_register(
        session, url=url, domain="immi.homeaffairs.gov.au",
        category="skillselect_summary", client=client,
    )
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    result = parse_skillselect_summary(text)
    if result.skipped:
        logger.warning("skillselect_summary: skipped %d malformed row(s)", result.skipped)

    written: list = []
    written += _persist_round_totals(session, result.round_totals, url, retrieved_at)
    written += _persist_monthly_invitations(session, result.monthly_invitations, url, retrieved_at)
    written += _persist_state_nominations(session, result.state_nominations, url, retrieved_at)

    session.commit()
    logger.info(
        "skillselect_summary: %d round totals, %d monthly rows, %d state "
        "nomination rows parsed; %d written",
        len(result.round_totals), len(result.monthly_invitations),
        len(result.state_nominations), len(written),
    )
    rows = _RowsWithSkipCount(written)
    rows.skipped = result.skipped
    return rows


def _persist_round_totals(session, rows, url, retrieved_at) -> list[EoiRoundTotal]:
    written = []
    for row in rows:
        existing = session.scalar(
            select(EoiRoundTotal).where(
                EoiRoundTotal.visa_label == row.visa_label,
                EoiRoundTotal.round_date == row.round_date,
            )
        )
        if existing is None:
            record = EoiRoundTotal(
                visa_code=row.visa_code, visa_label=row.visa_label,
                round_date=row.round_date, total_invited=row.total_invited,
                tie_break_date=row.tie_break_date,
                source_url=url, retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
            session.add(record)
            written.append(record)
        elif existing.total_invited != row.total_invited:
            existing.total_invited = row.total_invited
            existing.tie_break_date = row.tie_break_date
            existing.retrieved_at = retrieved_at
            written.append(existing)
    return written


def _persist_monthly_invitations(session, rows, url, retrieved_at) -> list[EoiInvitationMonthly]:
    written = []
    for row in rows:
        existing = session.scalar(
            select(EoiInvitationMonthly).where(
                EoiInvitationMonthly.visa_label == row.visa_label,
                EoiInvitationMonthly.program_year == row.program_year,
                EoiInvitationMonthly.month == row.month,
            )
        )
        if existing is None:
            record = EoiInvitationMonthly(
                visa_code=row.visa_code, visa_label=row.visa_label,
                program_year=row.program_year, month=row.month,
                invited_count=row.invited_count,
                source_url=url, retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
            session.add(record)
            written.append(record)
        elif existing.invited_count != row.invited_count:
            existing.invited_count = row.invited_count
            existing.retrieved_at = retrieved_at
            written.append(existing)
    return written


def _persist_state_nominations(session, rows, url, retrieved_at) -> list[EoiStateNomination]:
    written = []
    for row in rows:
        existing = session.scalar(
            select(EoiStateNomination).where(
                EoiStateNomination.visa_label == row.visa_label,
                EoiStateNomination.state_code == row.state_code,
                EoiStateNomination.period_start == row.period_start,
                EoiStateNomination.period_end == row.period_end,
            )
        )
        if existing is None:
            record = EoiStateNomination(
                visa_code=row.visa_code, visa_label=row.visa_label,
                state_code=row.state_code,
                period_start=row.period_start, period_end=row.period_end,
                nominated_count=row.nominated_count, suppressed=row.suppressed,
                source_url=url, retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
            session.add(record)
            written.append(record)
        elif (existing.nominated_count, existing.suppressed) != (row.nominated_count, row.suppressed):
            existing.nominated_count = row.nominated_count
            existing.suppressed = row.suppressed
            existing.retrieved_at = retrieved_at
            written.append(existing)
    return written
