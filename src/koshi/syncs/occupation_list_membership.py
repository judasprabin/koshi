import datetime as dt
import logging
import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_text
from koshi.extraction.lin19051 import ANZSCO_EDITION, parse_lin_occupation_lists
from koshi.models.occupation_list_membership import OccupationListMembership
from koshi.models.occupations import Occupation
from koshi.pipeline import _RowsWithSkipCount
from koshi.sources import LIN19051

logger = logging.getLogger(__name__)

# LIN19051_URL pins the compilation via its own path segments
# (.../<date>/<date>/text/...) — the compilation this run reflects, not
# guessed at or defaulted to today's date.
_COMPILATION_DATE_RE = re.compile(r"/(\d{4}-\d{2}-\d{2})/\d{4}-\d{2}-\d{2}/")


def _compilation_date(url: str) -> dt.date:
    match = _COMPILATION_DATE_RE.search(url)
    if match is None:
        raise ValueError(
            f"could not find a compilation date in {url!r} - LIN19051_URL's "
            f"shape may have changed"
        )
    return dt.date.fromisoformat(match.group(1))


def sync_occupation_list_membership(
    session: Session,
    *,
    url: str = LIN19051.url,
    client: httpx.Client | None = None,
) -> list[OccupationListMembership]:
    """Load current MLTSSL/STSOL/ROL membership (data model C20).

    Reuses the already-built `parse_lin_occupation_lists` (LIN 19/051
    Tables 1-3) — issue #21 needed only this persistence layer, not a new
    parser. `list_change_log` (C13) is deliberately not built here: per
    the data model doc, it's a *derivative* of this table (diff two
    `compilation_date`s), and there's only one compilation loaded so far.

    Codes that don't resolve against `occupations` are skipped, not
    written with a dangling FK — per-row isolation, matching every other
    sync in this codebase. Not expected to be common (sync_occupation_titles
    runs earlier in __main__.py's step order and adds 2013-only codes),
    but a source that's ever slightly ahead of the crosswalk must not
    crash the batch.
    """
    text = fetch_text(
        url, domain="www.legislation.gov.au", category="lin19051", client=client
    )
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    compilation_date = _compilation_date(url)

    lists = parse_lin_occupation_lists(text)

    written: list[OccupationListMembership] = []
    skipped = 0
    for list_name, codes in lists.items():
        for code in codes:
            if session.get(Occupation, code) is None:
                skipped += 1
                continue
            existing = session.scalar(
                select(OccupationListMembership).where(
                    OccupationListMembership.list_name == list_name,
                    OccupationListMembership.occupation_code == code,
                    OccupationListMembership.compilation_date == compilation_date,
                )
            )
            if existing is None:
                record = OccupationListMembership(
                    list_name=list_name, occupation_code=code,
                    anzsco_edition=ANZSCO_EDITION, compilation_date=compilation_date,
                    source_url=url, retrieved_at=retrieved_at,
                    reliability_tier="official_scraped",
                )
                session.add(record)
                written.append(record)
            # Membership as of a given compilation_date doesn't change —
            # nothing to update on an existing row, unlike a value that
            # can drift between runs.

    session.commit()
    logger.info(
        "occupation_list_membership: %d written, %d skipped (code not in occupations)",
        len(written), skipped,
    )
    rows = _RowsWithSkipCount(written)
    rows.skipped = skipped
    return rows
