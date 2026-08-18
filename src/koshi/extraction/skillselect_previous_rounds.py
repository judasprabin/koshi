"""Parser for the SkillSelect *previous rounds* archive.

The current invitation-rounds page publishes one round. Momentum needs a
trailing window of three, so without history every occupation's trend is
null - this page is what makes the trend real.

It differs from the current-round page in three ways that all matter:

1. **JSON root key is `criteria`, not `content`**, and each item carries its
   HTML under `description`, not `block`. Two independent shape differences
   on the same site.
2. **The round date is on the item** (`title`), which is more trustworthy
   than the HTML heading - the heading's `id` is demonstrably stale
   (`id="invitations-issued-13062024"` above text reading "13 November 2025").
3. **The occupation table's shape varies by round.** Recent rounds use one
   column *per visa subclass*:

       Occupation* | 189  | 491
       Actuary     | 85   | N/A*

   while older rounds use a single score column, with the subclass named in
   the header (`Subclass 189`) or only in the round-summary table.

Of the 19 archived rounds, only 4 carry an occupation table at all; the
rest are summary-only and are skipped rather than treated as failures.
"""

import dataclasses
import datetime as dt
import logging
import re

from bs4 import BeautifulSoup

from koshi.extraction.homeaffairs import HiddenFieldError, decode_hidden_field_items
from koshi.models.eoi_rounds import EoiRound
from koshi.provenance import require_provenance
from koshi.resilience import parse_int_loose

logger = logging.getLogger(__name__)

JSON_ROOT_KEY = "criteria"
BLOCK_KEY = "description"
OCCUPATION_TABLE_HEADING = "by occupation"

_SUBCLASS_RE = re.compile(r"\b(\d{3})\b")
# "N/A*", "N/A", "-" all mean "not invited in this subclass this round".
_NOT_INVITED = {"", "-", "–", "n/a", "n/a*", "na"}


@dataclasses.dataclass
class ParseResult:
    rows: list[EoiRound]
    skipped: int
    rounds_parsed: int
    rounds_without_occupations: int


def _round_date(title: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(title.strip(), "%d %B %Y").date()
    except ValueError:
        return None


def _occupation_table(description_html: str):
    soup = BeautifulSoup(description_html, "lxml")
    for heading in soup.find_all(["h2", "h3", "h4", "h5"]):
        if OCCUPATION_TABLE_HEADING in heading.get_text(" ", strip=True).casefold():
            return heading.find_next("table")
    return None


def _summary_subclass(description_html: str) -> str | None:
    """Read the subclass from the round-summary table, for rounds whose
    occupation table does not name it in the header."""
    soup = BeautifulSoup(description_html, "lxml")
    table = soup.find("table")
    body = table.find("tbody") if table else None
    if body is None:
        return None
    match = _SUBCLASS_RE.search(body.get_text(" ", strip=True))
    return match.group(1) if match else None


def _column_subclasses(table, fallback: str | None) -> dict[int, str]:
    """Map each score column index to the visa subclass it reports.

    A 3-column round names a subclass per column (`189`, `491`); a 2-column
    round names it in the header (`Subclass 189`) or not at all, in which
    case the summary table's subclass applies.
    """
    headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]
    mapping: dict[int, str] = {}
    for index, header in enumerate(headers[1:], start=1):
        match = _SUBCLASS_RE.search(header)
        if match:
            mapping[index] = match.group(1)
        elif fallback:
            mapping[index] = fallback
    if not mapping and fallback:
        # No <th> at all - assume a single score column.
        mapping[1] = fallback
    return mapping


def parse_skillselect_previous_rounds(
    page_html: str, *, source_url: str, retrieved_at: dt.datetime
) -> ParseResult:
    """Extract historical EOI rounds from the previous-rounds archive."""
    require_provenance(
        reliability_tier="official_scraped", source_url=source_url, retrieved_at=retrieved_at
    )

    items = decode_hidden_field_items(page_html, root_key=JSON_ROOT_KEY)
    if not items:
        raise HiddenFieldError(f"no rounds found under {JSON_ROOT_KEY!r}")

    rows: list[EoiRound] = []
    skipped = 0
    parsed = 0
    without = 0

    for item in items:
        title = item.get("title", "")
        description = item.get(BLOCK_KEY, "")
        round_date = _round_date(title)
        if round_date is None:
            logger.warning("skipping round with unparseable title %r", title)
            skipped += 1
            continue

        table = _occupation_table(description)
        body = table.find("tbody") if table else None
        if body is None:
            # Most archived rounds publish summary figures only. That is
            # normal history, not a parse failure.
            without += 1
            continue

        subclasses = _column_subclasses(table, _summary_subclass(description))
        if not subclasses:
            logger.warning("round %s: no subclass could be determined", title)
            skipped += 1
            continue

        parsed += 1
        for row in body.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2 or not cells[0]:
                skipped += 1
                continue
            name = cells[0]
            for index, visa_code in subclasses.items():
                if index >= len(cells):
                    continue
                raw = cells[index]
                if raw.strip().casefold().rstrip("*") in _NOT_INVITED:
                    continue  # not invited in this subclass - not a failure
                points = parse_int_loose(raw)
                if points is None:
                    skipped += 1
                    continue
                rows.append(
                    EoiRound(
                        visa_code=visa_code,
                        occupation_name_raw=name,
                        occupation_code=None,
                        round_date=round_date,
                        threshold_points=points,
                        invitations_issued=None,
                        source_url=source_url,
                        retrieved_at=retrieved_at,
                        reliability_tier="official_scraped",
                    )
                )

    if parsed == 0:
        raise HiddenFieldError(
            f"none of the {len(items)} archived rounds yielded an occupation "
            f"table - possible page redesign"
        )
    return ParseResult(
        rows=rows, skipped=skipped, rounds_parsed=parsed, rounds_without_occupations=without
    )
