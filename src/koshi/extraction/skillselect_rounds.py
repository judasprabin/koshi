"""Parser for the SkillSelect invitation-rounds page.

Rewritten 2026-08-18 against the live page. The previous implementation
looked for a three-column `<table id="round-results">`; the page has no
table markup at all and the occupation table has two columns, so every row
failed to unpack, was caught by the per-row handler, and was skipped - a
100% skip rate that reported a clean run.

The page decodes (see `koshi.extraction.homeaffairs`) into content blocks
holding three tables:

    A. Visa subclass | Total EOIs Invited | Tie break date   (1 row)
    B. Occupation | minimum score                            (140 rows)
    C. Visa subclass | Jul..Jun monthly matrix               (2 rows)

Table B is the one `eoi_rounds` needs. It has **no `<th>` headers at all**,
so it is located by its preceding heading rather than by header text or a
positional index.
"""

import dataclasses
import datetime as dt
import logging
import re

from bs4 import BeautifulSoup

from koshi.extraction.homeaffairs import (
    HiddenFieldError,
    assert_table_shape,
    decode_hidden_field,
    find_table_after_heading,
)
from koshi.models.eoi_rounds import EoiRound
from koshi.provenance import require_provenance
from koshi.resilience import parse_int_loose

logger = logging.getLogger(__name__)

JSON_ROOT_KEY = "content"
OCCUPATION_TABLE_HEADING = "by occupation and minimum score"
ROUND_DATE_HEADING = "invitations issued on"

# The live page's occupation table carries 140 rows. The floor is set well
# below that so ordinary churn passes, while a collapse to a handful of rows
# (the signature of a redesign) fails.
MIN_OCCUPATION_ROWS = 50

_ROUND_DATE_RE = re.compile(r"invitations issued on\s+(\d{1,2}\s+\w+\s+\d{4})", re.I)
_SUBCLASS_RE = re.compile(r"subclass\s+(\d{3})", re.I)


@dataclasses.dataclass
class ParseResult:
    rows: list[EoiRound]
    skipped: int


def _parse_round_date(blocks: list[str]) -> dt.date:
    """Read the round date from the 'Invitations issued on <date>' heading.

    Note the heading's own `id` attribute is unreliable - the live page
    carries id="invitations-issued-13062024" above text reading "4 June
    2026" - so the visible text is authoritative.
    """
    for block in blocks:
        match = _ROUND_DATE_RE.search(BeautifulSoup(block, "lxml").get_text(" ", strip=True))
        if match:
            return dt.datetime.strptime(match.group(1), "%d %B %Y").date()
    raise HiddenFieldError(
        "round date heading not found - expected 'Invitations issued on <date>'"
    )


def _parse_visa_code(blocks: list[str]) -> str:
    """Read the subclass from the round-summary table (Table A)."""
    for block in blocks:
        if ROUND_DATE_HEADING not in block.lower():
            continue
        table = find_table_after_heading(block, heading_contains=ROUND_DATE_HEADING)
        body = table.find("tbody")
        if body is None:
            continue
        match = _SUBCLASS_RE.search(body.get_text(" ", strip=True))
        if match:
            return match.group(1)
    raise HiddenFieldError(
        "visa subclass not found in the round-summary table - possible page redesign"
    )


def parse_skillselect_rounds(
    page_html: str, *, source_url: str, retrieved_at: dt.datetime
) -> ParseResult:
    """Extract one EoiRound per occupation from the invitation-rounds page.

    `visa_code` and `round_date` are read from the page rather than passed
    in, so they cannot drift from the data they label.

    Raises:
        HiddenFieldError: on any page-level problem - missing hidden field,
            missing heading, or a table whose shape is not what we parse.
            These are redesigns, and must fail loudly rather than yield an
            empty result.
    """
    require_provenance(
        reliability_tier="official_scraped", source_url=source_url, retrieved_at=retrieved_at
    )

    blocks = decode_hidden_field(page_html, root_key=JSON_ROOT_KEY)
    round_date = _parse_round_date(blocks)
    visa_code = _parse_visa_code(blocks)

    block = next(
        (b for b in blocks if OCCUPATION_TABLE_HEADING in b.lower()), None
    )
    if block is None:
        raise HiddenFieldError(
            f"no content block contains a {OCCUPATION_TABLE_HEADING!r} heading "
            f"- possible page redesign"
        )

    table = find_table_after_heading(block, heading_contains=OCCUPATION_TABLE_HEADING)
    rows = assert_table_shape(
        table,
        expected_columns=2,
        min_rows=MIN_OCCUPATION_ROWS,
        description="SkillSelect occupation/minimum-score table",
    )

    results: list[EoiRound] = []
    skipped = 0
    for index, row in enumerate(rows):
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        occupation_name, threshold_text = cells

        # Shape is already asserted above, so anything caught here is a
        # genuine one-off data problem in an otherwise healthy table.
        threshold_points = parse_int_loose(threshold_text)
        if threshold_points is None or not occupation_name:
            logger.warning(
                "skipping SkillSelect row %d: cells=%r", index, cells
            )
            skipped += 1
            continue

        results.append(
            EoiRound(
                visa_code=visa_code,
                # The page publishes names only. occupation_code stays NULL
                # until the LIN-first crosswalk resolves it; inventing one
                # here would be fabrication.
                occupation_name_raw=occupation_name,
                occupation_code=None,
                round_date=round_date,
                threshold_points=threshold_points,
                # Per-round totals exist, but at round/subclass grain -
                # attributing them to each occupation would be wrong.
                invitations_issued=None,
                source_url=source_url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
    return ParseResult(rows=results, skipped=skipped)
