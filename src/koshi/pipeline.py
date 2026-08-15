import datetime as dt
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.anzsco_occupations import parse_anzsco_occupations
from koshi.extraction.skillselect_rounds import parse_skillselect_rounds
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupations import Occupation
from koshi.models.source_pages import SourcePage
from koshi.momentum import refresh_momentum

logger = logging.getLogger(__name__)


class _RowsWithSkipCount(list):
    """A plain list subclass that additionally carries the extraction
    parser's skip count (ParseResult.skipped).

    sync_anzsco_occupations/sync_skillselect_rounds's return type
    (list[Occupation]/list[EoiRound]) is relied on elsewhere (e.g.
    tests/test_pipeline.py) and must not change. Since it's still a real
    list, every existing caller (len(), iteration, `== []`, ...) keeps
    working unmodified; __main__.py's run summary can additionally read
    the bonus `.skipped` attribute via getattr(result, "skipped", None)
    to surface how many rows a run silently dropped, without either side
    needing a wider return-type change.
    """

    skipped: int = 0


ANZSCO_URL = "https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco"
SKILLSELECT_ROUNDS_URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"

# A stand-in for "never extracted" that compares less than any real
# last_changed_at, so a page with no last_extracted_at watermark always
# looks due for extraction.
_NEVER_EXTRACTED = dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _needs_extraction(page: SourcePage) -> bool:
    """Whether this page's content has changed since it was last
    successfully parsed.

    Deliberately NOT the `changed` bool fetch_and_register returns:
    fetch_and_register commits content_hash/last_changed_at before parsing
    is even attempted, so if parsing raised last time, `changed` would be
    False on the next run (the hash hasn't moved) and the page would be
    silently skipped forever. Comparing last_changed_at against our own
    last_extracted_at watermark instead means a prior parse failure (which
    leaves last_extracted_at untouched) is retried on every subsequent run.
    """
    watermark = page.last_extracted_at or _NEVER_EXTRACTED
    return page.last_changed_at > watermark


def sync_anzsco_occupations(
    session: Session, *, url: str = ANZSCO_URL, client: httpx.Client | None = None
) -> list[Occupation]:
    page, _changed, text = fetch_and_register(
        session, url=url, domain="www.jobsandskills.gov.au", category="anzsco_occupations", client=client
    )
    if not _needs_extraction(page):
        return []

    result = parse_anzsco_occupations(
        text, source_url=url, retrieved_at=dt.datetime.now(dt.timezone.utc)
    )
    if result.skipped:
        logger.warning("anzsco_occupations: skipped %d malformed row(s)", result.skipped)
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


def sync_skillselect_rounds(
    session: Session,
    *,
    url: str = SKILLSELECT_ROUNDS_URL,
    visa_code: str = "189",
    client: httpx.Client | None = None,
) -> list[EoiRound]:
    page, _changed, text = fetch_and_register(
        session, url=url, domain="immi.homeaffairs.gov.au", category="skillselect_rounds", client=client
    )
    if not _needs_extraction(page):
        return []

    parse_result = parse_skillselect_rounds(
        text,
        visa_code=visa_code,
        source_url=url,
        retrieved_at=dt.datetime.now(dt.timezone.utc),
    )
    if parse_result.skipped:
        logger.warning("skillselect_rounds: skipped %d malformed row(s)", parse_result.skipped)

    # Upsert by (visa_code, occupation_code, round_date): a whole-page hash
    # change (build stamp, "last reviewed" date) re-parses the same round
    # data and must not manufacture duplicate rows / fake momentum.
    #
    # The DB existence check alone isn't enough to dedup rows *within* this
    # same batch: the production session (koshi.db.SessionLocal) sets
    # autoflush=False, so an earlier session.add() in this loop is never
    # flushed before the next iteration's SELECT runs. If a single scraped
    # page contains two rows with an identical (visa_code, occupation_code,
    # round_date) — plausible in messy government HTML tables — both would
    # pass the "not found in DB" check, both would be queued, and the
    # batch commit below would then raise an unhandled UniqueViolation,
    # rolling back every valid new round from that page. Tracking keys
    # already staged in this call closes that gap.
    new_rounds = []
    staged_keys: set[tuple[str, str | None, dt.date]] = set()
    for round_ in parse_result.rows:
        key = (round_.visa_code, round_.occupation_code, round_.round_date)
        if key in staged_keys:
            continue
        existing = session.scalar(
            select(EoiRound).where(
                EoiRound.visa_code == round_.visa_code,
                EoiRound.occupation_code == round_.occupation_code,
                EoiRound.round_date == round_.round_date,
            )
        )
        if existing is not None:
            continue
        session.add(round_)
        staged_keys.add(key)
        new_rounds.append(round_)
    # Only advance the extraction watermark once parsing AND persisting
    # have both succeeded — see sync_anzsco_occupations above.
    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()

    # Recompute momentum for every occupation touched by a genuinely new
    # round — nothing else in the system ever calls refresh_momentum, so
    # without this, occupation_momentum rows are never produced end-to-end
    # and GET /v1/occupations always shows momentum: null.
    #
    # Isolated per code: one occupation's momentum computation failing must
    # not prevent the others from being refreshed, and must not undo the
    # round persistence that already committed above.
    new_codes = {r.occupation_code for r in new_rounds if r.occupation_code is not None}
    for code in new_codes:
        try:
            refresh_momentum(session, code)
        except Exception:
            # Roll back before logging: against the real Postgres-backed
            # session this codebase uses, a genuine DB-level failure
            # (constraint violation, stale row, connection hiccup) leaves
            # the session's transaction deactivated — every subsequent
            # operation on it raises until rollback() runs. Without this,
            # the *next* occupation code's refresh_momentum call would
            # itself raise on the still-poisoned transaction and get
            # logged as a spurious failure, cascading one real failure
            # into every occupation processed afterward.
            session.rollback()
            logger.exception("momentum refresh failed for occupation_code=%s", code)

    rows = _RowsWithSkipCount(new_rounds)
    rows.skipped = parse_result.skipped
    return rows
