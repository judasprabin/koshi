import datetime as dt
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register, fetch_text
from koshi.extraction.anzsco_occupations import (
    ParseResult,
    has_next_page,
    parse_anzsco_occupations,
)
from koshi.extraction.skillselect_rounds import parse_skillselect_rounds
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupations import Occupation
from koshi.models.source_pages import SourcePage
from koshi.momentum import refresh_momentum
from koshi.resilience import Throttler

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

# The live listing is 103 pages (1,236 results at 12 per page). The cap sits
# above that as a runaway guard; it is not a deliberate truncation.
ANZSCO_MAX_PAGES = 150
# Politeness between sequential requests to a single government host. This
# is the first koshi run that fetches many pages from one domain, and the
# reason resilience.Throttler exists.
ANZSCO_PAGE_INTERVAL_SECONDS = 1.0

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
    session: Session,
    *,
    url: str = ANZSCO_URL,
    client: httpx.Client | None = None,
    max_pages: int = ANZSCO_MAX_PAGES,
) -> list[Occupation]:
    page, _changed, text = fetch_and_register(
        session, url=url, domain="www.jobsandskills.gov.au", category="anzsco_occupations", client=client
    )
    if not _needs_extraction(page):
        return []

    retrieved_at = dt.datetime.now(dt.timezone.utc)
    result = parse_anzsco_occupations(text, source_url=url, retrieved_at=retrieved_at)
    rows = list(result.rows)
    skipped = result.skipped

    # The listing paginates at 12 cards over 103 pages: without following
    # the pager koshi loads 12 of 1,236 occupations. Only page 1 is
    # registered in source_pages — the pages change together, so 103
    # registry rows would add no signal.
    #
    # max_pages is a guard against a pager loop, not a policy choice: it is
    # set above the real page count, so hitting it means the page changed
    # shape and is worth a warning.
    throttle = Throttler(ANZSCO_PAGE_INTERVAL_SECONDS)
    current = 0
    while has_next_page(text, current_page=current) and current + 1 < max_pages:
        current += 1
        throttle.wait()
        page_url = f"{url}?page={current}"
        text = fetch_text(
            page_url,
            domain="www.jobsandskills.gov.au",
            category="anzsco_occupations",
            client=client,
        )
        page_result = parse_anzsco_occupations(
            text, source_url=page_url, retrieved_at=retrieved_at
        )
        rows.extend(page_result.rows)
        skipped += page_result.skipped
    else:
        if current + 1 >= max_pages and has_next_page(text, current_page=current):
            logger.warning(
                "anzsco_occupations: stopped at the %d-page cap with more pages "
                "advertised — the pager may have changed shape",
                max_pages,
            )

    result = ParseResult(rows=rows, skipped=skipped)
    if result.skipped:
        logger.warning("anzsco_occupations: skipped %d malformed row(s)", result.skipped)
    logger.info(
        "anzsco_occupations: parsed %d occupations across %d page(s)",
        len(result.rows), current + 1,
    )
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


def refresh_momentum_for_codes(session: Session, codes: set[str]) -> None:
    """Recompute momentum for each occupation code, isolated per code.

    Nothing else in the system calls refresh_momentum, so without this
    `occupation_momentum` rows are never produced end-to-end and
    GET /v1/occupations always shows momentum: null.

    One occupation's failure must not prevent the others from refreshing,
    and must not undo work that already committed.
    """
    for code in codes:
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


def sync_skillselect_rounds(
    session: Session,
    *,
    url: str = SKILLSELECT_ROUNDS_URL,
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

    # Upsert by (visa_code, occupation_name_raw, round_date): a whole-page
    # hash change (build stamp, "last reviewed" date) re-parses the same
    # round data and must not manufacture duplicate rows / fake momentum.
    #
    # Keyed on the name, not the code. SkillSelect publishes occupation
    # names only, so occupation_code is NULL on every scraped row until the
    # crosswalk lands — and since Postgres treats NULLs as distinct, a
    # code-keyed check would match nothing and re-insert all 140 rows on
    # every run.
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
    staged_keys: set[tuple[str, str, dt.date]] = set()
    for round_ in parse_result.rows:
        key = (round_.visa_code, round_.occupation_name_raw, round_.round_date)
        if key in staged_keys:
            continue
        existing = session.scalar(
            select(EoiRound).where(
                EoiRound.visa_code == round_.visa_code,
                EoiRound.occupation_name_raw == round_.occupation_name_raw,
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
