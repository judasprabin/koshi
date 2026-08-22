import datetime as dt
import logging

import httpx
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.skillselect_previous_rounds import (
    parse_skillselect_previous_rounds,
)
from koshi.models.eoi_rounds import EoiRound
from koshi.pipeline import (
    _RowsWithSkipCount,
    _needs_extraction,
    _persist_rounds,
    refresh_momentum_for_codes,
    resolve_round_occupation_codes,
)
from koshi.sources import SKILLSELECT_PREVIOUS_ROUNDS

logger = logging.getLogger(__name__)


def sync_skillselect_previous_rounds(
    session: Session,
    *,
    url: str = SKILLSELECT_PREVIOUS_ROUNDS.url,
    client: httpx.Client | None = None,
) -> list[EoiRound]:
    """Backfill historical EOI rounds from the previous-rounds archive.

    The current-round page publishes one round; momentum needs a trailing
    window of three, so without this every occupation's trend is null. Of
    19 archived rounds, 4 carry occupation tables.
    """
    page, _changed, text = fetch_and_register(
        session, url=url, domain="immi.homeaffairs.gov.au",
        category="skillselect_previous_rounds", client=client,
    )
    if not _needs_extraction(page):
        return []

    result = parse_skillselect_previous_rounds(
        text, source_url=url, retrieved_at=dt.datetime.now(dt.timezone.utc)
    )
    logger.info(
        "previous_rounds: %d rounds parsed, %d summary-only, %d rows, %d skipped",
        result.rounds_parsed, result.rounds_without_occupations,
        len(result.rows), result.skipped,
    )
    resolve_round_occupation_codes(session, result.rows)
    new_rounds = _persist_rounds(session, result.rows)

    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()

    refresh_momentum_for_codes(
        session, {r.occupation_code for r in new_rounds if r.occupation_code}
    )
    rows = _RowsWithSkipCount(new_rounds)
    rows.skipped = result.skipped
    return rows
