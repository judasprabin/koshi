"""Parser for LIN 19/051, the binding skilled-occupation instrument.

`Migration (LIN 19/051: Specification of Occupations and Relevant Assessing
Authorities) Instrument 2019` is the legal source for which occupations are
on MLTSSL/STSOL/ROL and which authority assesses each one. It is also - and
this is why koshi parses it first - an authoritative occupation name -> ANZSCO
code mapping, because it is the instrument migration decisions are actually
made under.

The register page is a shell; the instrument body is one iframe-hop away at
a static epub HTML document. That document holds 12 tables, **none of which
carry an id or class**, so they can only be addressed by position:

    index 1  MLTSSL          212 occupations
    index 2  STSOL           215 occupations
    index 3  ROL              77 occupations
    index 5  occupation -> assessing authority, 504 rows
    index 6  assessing-body key, 38 rows

A positional index silently returns the wrong table if the document gains
one, so every read asserts an expected row count. That assertion is the only
thing standing between a re-ordered document and quietly loading MLTSSL rows
as if they were the assessing-authority list.

Note the instrument is coded against **ANZSCO 2013**, not 2022 - 25 of its
codes are absent from the 2022 edition. Rows are tagged accordingly.
"""

import dataclasses
import logging
import re
import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

logger = logging.getLogger(__name__)

# The epub is served as XHTML; BeautifulSoup warns when an HTML parser is
# pointed at it. lxml handles it correctly, so the warning is noise.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ANZSCO_EDITION = "2013"

TITLE_TABLE_INDEX = 5
TITLE_TABLE_ROWS = 505  # 504 data rows + 1 header

# (list name, table index, expected total rows incl. header)
LIN_LIST_TABLES = (
    ("MLTSSL", 1, 213),
    ("STSOL", 2, 216),
    ("ROL", 3, 78),
)

_DIGITS_RE = re.compile(r"\d+")


class Lin19051Error(ValueError):
    """The instrument did not have the expected table structure."""


@dataclasses.dataclass
class LinTitle:
    title: str
    occupation_code: str
    assessing_authority: str
    anzsco_edition: str = ANZSCO_EDITION


@dataclasses.dataclass
class ParseResult:
    rows: list[LinTitle]
    skipped: int


def _table_at(html: str, index: int, expected_rows: int):
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if len(tables) <= index:
        raise Lin19051Error(
            f"expected a table at position {index}, document has {len(tables)} "
            f"- possible restructure"
        )
    table = tables[index]
    rows = table.find_all("tr")
    if len(rows) != expected_rows:
        raise Lin19051Error(
            f"table at position {index} has {len(rows)} rows, expected "
            f"{expected_rows}. These tables have no id/class and are addressed "
            f"positionally, so a row-count mismatch means the wrong table - "
            f"refusing to load it as if it were the right one."
        )
    return rows


def _cells(row) -> list[str]:
    return [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]


def parse_lin_titles(html: str) -> ParseResult:
    """Parse table 5: occupation -> ANZSCO code -> assessing authority."""
    rows = _table_at(html, TITLE_TABLE_INDEX, TITLE_TABLE_ROWS)

    out: list[LinTitle] = []
    skipped = 0
    for index, row in enumerate(rows[1:], start=1):
        cells = _cells(row)
        if len(cells) < 3:
            logger.warning("skipping LIN table-5 row %d: %d cells", index, len(cells))
            skipped += 1
            continue

        title = cells[1].strip()
        match = _DIGITS_RE.search(cells[2])
        code = match.group() if match else ""
        if not title or len(code) != 6:
            logger.warning("skipping LIN table-5 row %d: %r", index, cells[:3])
            skipped += 1
            continue

        out.append(
            LinTitle(
                title=title,
                occupation_code=code,
                assessing_authority=cells[3].strip() if len(cells) > 3 else "",
            )
        )
    return ParseResult(rows=out, skipped=skipped)


def parse_lin_occupation_lists(html: str) -> dict[str, list[str]]:
    """Parse tables 1-3: MLTSSL / STSOL / ROL membership by ANZSCO code.

    Returned for use by the occupation-list membership table (data model
    C20); not consumed by the crosswalk itself.
    """
    lists: dict[str, list[str]] = {}
    for name, index, expected_rows in LIN_LIST_TABLES:
        codes: list[str] = []
        for row in _table_at(html, index, expected_rows)[1:]:
            cells = _cells(row)
            if len(cells) < 3:
                continue
            match = _DIGITS_RE.search(cells[2])
            if match and len(match.group()) == 6:
                codes.append(match.group())
        lists[name] = codes
    return lists
