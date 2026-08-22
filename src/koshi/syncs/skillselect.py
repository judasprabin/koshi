import datetime as dt
import logging

import httpx
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.skillselect_rounds import parse_skillselect_rounds
from koshi.models.eoi_rounds import EoiRound
from koshi.pipeline import (
    _RowsWithSkipCount,
    _needs_extraction,
    _persist_rounds,
    refresh_momentum_for_codes,
    resolve_round_occupation_codes,
)
from koshi.sources import SKILLSELECT_ROUNDS

logger = logging.getLogger(__name__)


def sync_skillselect_rounds(
    session: Session,
    *,
    url: str = SKILLSELECT_ROUNDS.url,
    client: httpx.Client | None = None,
) -> list[EoiRound]:
    # visa_code is no longer a caller-supplied default: the parser reads the
    # subclass from the page's own round-summary table, so the label can't
    # drift from the data it describes.
    page, _changed, text = fetch_and_register(
        session, url=url, domain="immi.homeaffairs.gov.au", category="skillselect_rounds", client=client
    )
    if not _needs_extraction(page):
        return []

    parse_result = parse_skillselect_rounds(
        text,
        source_url=url,
        retrieved_at=dt.datetime.now(dt.timezone.utc),
    )
    if parse_result.skipped:
        logger.warning("skillselect_rounds: skipped %d malformed row(s)", parse_result.skipped)

    resolve_round_occupation_codes(session, parse_result.rows)

    # Upsert by (visa_code, occupation_name_raw, round_date): a whole-page
    # hash change (build stamp, "last reviewed" date) re-parses the same
    # round data and must not manufacture duplicate rows / fake momentum.
    # See _persist_rounds for why the key is the name and why in-batch
    # dedup is also required. Shared with the previous-rounds sync, whose
    # archive genuinely overlaps this page.
    new_rounds = _persist_rounds(session, parse_result.rows)
    # Only advance the extraction watermark once parsing AND persisting
    # have both succeeded — see syncs.anzsco.sync_anzsco_occupations above.
    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()

    # NOTE: SkillSelect publishes occupation *names*, not ANZSCO codes, so
    # every scraped round currently has occupation_code = NULL and this set
    # is empty — momentum is not refreshed from scraping until the
    # name->code crosswalk lands. The call stays wired up so the crosswalk
    # is the only missing piece, and refresh_momentum_for_codes remains
    # directly tested in the meantime.
    new_codes = {r.occupation_code for r in new_rounds if r.occupation_code is not None}
    refresh_momentum_for_codes(session, new_codes)

    rows = _RowsWithSkipCount(new_rounds)
    rows.skipped = parse_result.skipped
    return rows
