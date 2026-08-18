import datetime as dt
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register, fetch_bytes, fetch_text
from koshi.crosswalk import normalize_title, resolve_occupation_code
from koshi.extraction.anzsco_occupations import (
    ParseResult,
    has_next_page,
    parse_anzsco_occupations,
)
from koshi.extraction.abs_anzsco import (
    ANZSCO_EDITION as ABS_ANZSCO_EDITION,
    parse_abs_occupations,
    parse_abs_titles,
)
from koshi.extraction.bp0068 import parse_bp0068_grants
from koshi.extraction.lin19051 import parse_lin_titles
from koshi.extraction.skillselect_previous_rounds import (
    parse_skillselect_previous_rounds,
)
from koshi.extraction.skillselect_rounds import parse_skillselect_rounds
from koshi.models.application_funnel import ApplicationFunnel
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupation_titles import OccupationTitle
from koshi.models.occupations import Occupation
from koshi.models.source_pages import SourcePage
from koshi.models.visa_subclasses import VisaSubclass
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
SKILLSELECT_PREVIOUS_ROUNDS_URL = (
    "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/previous-rounds"
)
# The instrument body, one iframe-hop from the register page. The date
# segments pin the compilation; bump them when a new compilation lands.
LIN19051_URL = (
    "https://www.legislation.gov.au/F2019L00278/2026-03-28/2026-03-28"
    "/text/original/epub/OEBPS/document_1/document_1.html"
)
BP0068_URL = (
    "https://data.gov.au/data/dataset/096fd157-807c-4ba0-8c63-0754cae4ba35/resource/"
    "832fe752-f672-4ce7-a5bc-bada2270496c/download/"
    "bp0068-migration-and-child-outcome-since-2015-16-to-2025-06-30-masked-v100.xlsx"
)
ABS_ANZSCO_URL = (
    "https://www.abs.gov.au/statistics/classifications/"
    "anzsco-australian-and-new-zealand-standard-classification-occupations/2022/"
    "anzsco%202022%20structure%20062023.xlsx"
)

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


def sync_abs_occupations(
    session: Session, *, url: str = ABS_ANZSCO_URL, client: httpx.Client | None = None
) -> list[Occupation]:
    """Load the occupation set from the ABS classification (Table 5).

    The JSA listing is a *browse UI*, and it surfaces only 878 of ANZSCO's
    1,076 six-digit occupations. That shortfall is not cosmetic: a live
    invitation round referenced 23 occupations that resolve to perfectly
    valid ANZSCO codes which simply were not in the JSA grid, so their
    rounds could not be linked at all.

    ABS is the classification's custodian, so its Table 5 is the
    authoritative occupation universe. JSA remains synced because it also
    publishes 4-digit unit groups (which NSW's list joins on) and is the
    cadence signal; the two merge by primary key.
    """
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    workbook = fetch_bytes(url, domain="www.abs.gov.au", category="abs_anzsco", client=client)
    result = parse_abs_occupations(workbook)

    written: list[Occupation] = []
    for row in result.rows:
        session.merge(
            Occupation(
                code=row.occupation_code,
                name=row.title,
                unit_group=row.occupation_code[:4],
                code_grain="occupation",
                anzsco_edition=ABS_ANZSCO_EDITION,
                source_url=url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
        written.append(row)
    session.commit()
    logger.info("abs_occupations: merged %d occupations", len(written))
    rows = _RowsWithSkipCount(written)
    rows.skipped = result.skipped
    return rows


def sync_occupation_titles(
    session: Session,
    *,
    lin_url: str = LIN19051_URL,
    abs_url: str = ABS_ANZSCO_URL,
    client: httpx.Client | None = None,
) -> list[OccupationTitle]:
    """Load the name->code crosswalk from both sources.

    Upserts by (title_normalized, title_source), so re-running replaces a
    source's mapping in place rather than accumulating duplicates.

    Both sources are loaded because neither is sufficient: against a live
    invitation round, each resolves 132/140 on its own and their union
    resolves 140/140.
    """
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    staged: dict[tuple[str, str], OccupationTitle] = {}

    lin_html = fetch_text(
        lin_url, domain="www.legislation.gov.au", category="lin19051", client=client
    )
    for row in parse_lin_titles(lin_html).rows:
        key = (normalize_title(row.title), "LIN_19_051")
        staged.setdefault(key, OccupationTitle(
            title=row.title, title_normalized=key[0],
            occupation_code=row.occupation_code, title_source="LIN_19_051",
            anzsco_edition=row.anzsco_edition, source_url=lin_url,
            retrieved_at=retrieved_at, reliability_tier="official_scraped",
        ))

    abs_bytes = fetch_bytes(
        abs_url, domain="www.abs.gov.au", category="abs_anzsco", client=client
    )
    for row in parse_abs_titles(abs_bytes).rows:
        key = (normalize_title(row.title), "ABS_ANZSCO")
        staged.setdefault(key, OccupationTitle(
            title=row.title, title_normalized=key[0],
            occupation_code=row.occupation_code, title_source="ABS_ANZSCO",
            anzsco_edition=row.anzsco_edition, source_url=abs_url,
            retrieved_at=retrieved_at, reliability_tier="official_scraped",
        ))

    # LIN 19/051 is coded against ANZSCO 2013 and names occupations the
    # 2022 classification does not contain - Cabinetmaker (394111) is
    # invited in live rounds and exists only there. Adding those as
    # edition-tagged occupation rows is what lets such rounds link at all;
    # without it the crosswalk resolves the name but the FK has no target.
    #
    # Only codes ABS does not already carry are added, so 2022 stays
    # authoritative wherever the editions overlap.
    existing_codes = {c for (c,) in session.execute(select(Occupation.code))}
    edition_only = 0
    for row in parse_lin_titles(lin_html).rows:
        if row.occupation_code in existing_codes:
            continue
        session.merge(
            Occupation(
                code=row.occupation_code,
                name=row.title,
                unit_group=row.occupation_code[:4],
                code_grain="occupation",
                anzsco_edition=row.anzsco_edition,
                source_url=lin_url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
        existing_codes.add(row.occupation_code)
        edition_only += 1
    if edition_only:
        logger.info(
            "occupation_titles: added %d ANZSCO-2013-only occupation(s) absent from 2022",
            edition_only,
        )

    written: list[OccupationTitle] = []
    for (normalized, source), row in staged.items():
        existing = session.scalar(
            select(OccupationTitle).where(
                OccupationTitle.title_normalized == normalized,
                OccupationTitle.title_source == source,
            )
        )
        if existing is None:
            session.add(row)
            written.append(row)
        elif existing.occupation_code != row.occupation_code:
            existing.occupation_code = row.occupation_code
            existing.retrieved_at = retrieved_at
            written.append(existing)
    session.commit()
    logger.info(
        "occupation_titles: %d staged, %d written", len(staged), len(written)
    )
    return written


def sync_skillselect_previous_rounds(
    session: Session,
    *,
    url: str = SKILLSELECT_PREVIOUS_ROUNDS_URL,
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


def _persist_rounds(session: Session, rounds: list[EoiRound]) -> list[EoiRound]:
    """Insert rounds not already stored, deduping within the batch too.

    Shared by the current-round and previous-rounds syncs, which overlap:
    a round can appear on both pages. Keyed on
    (visa_code, occupation_name_raw, round_date) — the name, not the code,
    because an unresolved row's code is NULL and Postgres treats NULLs as
    distinct, which would defeat the check entirely.

    The in-batch `staged_keys` set is required because the production
    session runs autoflush=False: an earlier session.add() is not flushed
    before the next iteration's SELECT, so two identical rows in one page
    would both pass the DB check and collide at commit.
    """
    new_rounds: list[EoiRound] = []
    staged_keys: set[tuple[str, str, dt.date]] = set()
    for round_ in rounds:
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
    return new_rounds


def sync_bp0068_grants(
    session: Session, *, url: str = BP0068_URL, client: httpx.Client | None = None
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

    for code, name, category in sorted(
        {(r.visa_code, r.visa_name, r.visa_category) for r in result.rows}
    ):
        session.merge(
            VisaSubclass(
                code=code, name=name, visa_category=category,
                source_url=url, retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
    session.flush()  # subclasses must exist before the funnel's FK is checked

    written: list[ApplicationFunnel] = []
    for row in result.rows:
        existing = session.scalar(
            select(ApplicationFunnel).where(
                ApplicationFunnel.visa_code == row.visa_code,
                ApplicationFunnel.program_year == row.program_year,
            )
        )
        if existing is None:
            record = ApplicationFunnel(
                visa_code=row.visa_code,
                program_year=row.program_year,
                granted_count=row.granted_count,
                source_url=url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
            session.add(record)
            written.append(record)
        elif existing.granted_count != row.granted_count:
            existing.granted_count = row.granted_count
            existing.retrieved_at = retrieved_at
            written.append(existing)
    session.commit()
    logger.info(
        "bp0068: %d records -> %d funnel rows (%d written)",
        result.record_count, len(result.rows), len(written),
    )
    rows = _RowsWithSkipCount(written)
    rows.skipped = result.skipped
    return rows


def backfill_unresolved_round_codes(session: Session) -> list[EoiRound]:
    """Retry code resolution for stored rounds that never resolved.

    Without this, a row unresolved once stays unresolved forever: the
    source page has not changed, so `_needs_extraction` returns False and
    the round is never revisited — even though the *crosswalk* may have
    grown since (a new source, a new edition, a normalisation fix).

    This is the case that actually bit: archived rounds naming
    `Cabinetmaker` were persisted before LIN 19/051's ANZSCO-2013-only
    occupations were loaded, so their FK target did not yet exist.

    Momentum is refreshed for anything newly resolved, since a round that
    only now has a code was not counted in any earlier trend.
    """
    pending = list(
        session.scalars(select(EoiRound).where(EoiRound.occupation_code.is_(None)))
    )
    if not pending:
        return []

    resolved = [r for r in pending if _apply_code(session, r)]
    session.commit()
    logger.info(
        "backfill: resolved %d of %d previously-unresolved round(s)",
        len(resolved), len(pending),
    )
    refresh_momentum_for_codes(session, {r.occupation_code for r in resolved})
    return resolved


def _apply_code(session: Session, round_: EoiRound) -> bool:
    """Resolve one round's code, honouring the occupations FK. Returns
    whether a code was written."""
    code = resolve_occupation_code(session, round_.occupation_name_raw)
    if code is None or session.get(Occupation, code) is None:
        return False
    round_.occupation_code = code
    return True


def resolve_round_occupation_codes(session: Session, rounds: list[EoiRound]) -> int:
    """Fill occupation_code on scraped rounds from the name crosswalk.

    Returns the number resolved. Rows the crosswalk cannot resolve keep
    occupation_code = NULL and their occupation_name_raw, so they stay
    re-resolvable once the crosswalk is extended — an unresolved name is
    recorded as unresolved rather than guessed at.

    A resolved code is only written if it actually exists in `occupations`,
    because `eoi_rounds.occupation_code` is an FK. The crosswalk carries
    codes koshi's occupation table legitimately does not have: LIN 19/051 is
    coded against ANZSCO 2013 (25 of its codes are absent from 2022), and
    the JSA listing koshi loads is 2022. Writing one of those would abort
    the whole batch on a foreign-key violation.
    """
    resolved = 0
    unresolved: list[str] = []
    missing_fk: list[str] = []
    for round_ in rounds:
        if round_.occupation_code is not None:
            continue
        code = resolve_occupation_code(session, round_.occupation_name_raw)
        if code is None:
            unresolved.append(round_.occupation_name_raw)
            continue
        if session.get(Occupation, code) is None:
            missing_fk.append(f"{round_.occupation_name_raw}->{code}")
            continue
        round_.occupation_code = code
        resolved += 1

    logger.info(
        "crosswalk: resolved %d/%d round occupations", resolved, len(rounds)
    )
    if unresolved:
        logger.warning(
            "crosswalk: %d occupation name(s) unresolved, e.g. %r",
            len(unresolved), unresolved[:5],
        )
    if missing_fk:
        logger.warning(
            "crosswalk: %d code(s) resolved but absent from occupations "
            "(edition mismatch?), e.g. %r",
            len(missing_fk), missing_fk[:5],
        )
    return resolved


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

    resolve_round_occupation_codes(session, parse_result.rows)

    # Upsert by (visa_code, occupation_name_raw, round_date): a whole-page
    # hash change (build stamp, "last reviewed" date) re-parses the same
    # round data and must not manufacture duplicate rows / fake momentum.
    # See _persist_rounds for why the key is the name and why in-batch
    # dedup is also required. Shared with the previous-rounds sync, whose
    # archive genuinely overlaps this page.
    new_rounds = _persist_rounds(session, parse_result.rows)
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
