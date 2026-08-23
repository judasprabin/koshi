"""Parser for the migration program planning-levels page (data model C15).

docs/superpowers/research/2026-08-16-koshi-source-urls.md corrects the
data model doc's stale claim that this needs manual PDF curation: the
audit found zero PDFs on the page — the full 3-year planning-levels table
is in the same hidden-field JSON every other Home Affairs page uses.

The table is a 3-year pivot (this year + next two) with row-spanning
categories and footnote markers in <sup> tags glued onto both labels and
values with no separating space. Three row shapes:

- 1 cell, colspan=5: a pure section divider ("Skilled Migration
  Program") — no data, skipped.
- 4 cells, colspan=2 on the first: either a derivable "Total ..." row
  (skipped) or a genuine leaf stream with no sub-category
  ("Special Eligibility", kept) — indistinguishable by HTML shape alone,
  only the "Total " text prefix tells them apart.
- 5 cells: category | stream | year1 | year2 | year3. The category cell
  is populated only on a stream's first row; continuation rows carry an
  empty first cell (a real row-span in the source, flattened to a
  blank cell by the JSON encoding) — category isn't part of C15's schema
  anyway, so this parser tracks it only enough to know a row is a
  continuation, not to store it.
"""

import copy
import dataclasses
import logging
import re

from bs4 import BeautifulSoup

from koshi.extraction.homeaffairs import HiddenFieldError, decode_hidden_field_items

logger = logging.getLogger(__name__)

DEFAULT_ROOT_KEY = "content"

# Handles both a plain hyphen and the source's en dash (2024–25).
_YEAR_RE = re.compile(r"(\d{4})[–-](\d{2})")


@dataclasses.dataclass
class AllocationRow:
    program_year: str
    stream_name: str
    places: int


@dataclasses.dataclass
class ParseResult:
    rows: list[AllocationRow]
    skipped: int


def _cell_text(cell) -> str:
    """Text content with any <sup> footnote marker removed — footnotes
    are glued onto the text with no separating space
    ("Talent and Innovation<sup>1</sup>", "3,500<sup>2</sup>"), so a
    plain get_text() would silently fold the footnote digit into the
    label or the number."""
    cell = copy.copy(cell)
    for sup in cell.find_all("sup"):
        sup.decompose()
    return cell.get_text(strip=True)


def _parse_places(text: str) -> int | None:
    cleaned = text.replace(",", "").strip()
    return int(cleaned) if cleaned.isdigit() else None


def parse_program_allocation(
    page_html: str, *, root_key: str = DEFAULT_ROOT_KEY
) -> ParseResult:
    items = decode_hidden_field_items(page_html, root_key=root_key)

    table_block = next(
        (i["block"] for i in items if "block" in i and "<table" in i["block"]),
        None,
    )
    if table_block is None:
        raise HiddenFieldError(
            "no content block carries a <table> - possible page redesign"
        )

    soup = BeautifulSoup(table_block, "lxml")
    table = soup.find("table")
    # Rows are split across interleaved <thead>/<tbody> sections (the
    # section-divider rows sit in their own <thead>) — search the whole
    # table, not one tbody, or the divider rows and everything after the
    # first one are silently missed.
    trs = table.find_all("tr")

    header_cells = trs[0].find_all(["th", "td"])
    years: list[str] = []
    for cell in header_cells[1:]:
        match = _YEAR_RE.search(_cell_text(cell))
        if match:
            years.append(f"{match.group(1)}-{match.group(2)}")

    rows: list[AllocationRow] = []
    skipped = 0
    for tr in trs[1:]:
        cells = tr.find_all(["th", "td"])
        if len(cells) == 1:
            continue  # section divider (colspan=5), no data
        if len(cells) == 4:
            label = _cell_text(cells[0])
            if not label or label.lower().startswith("total"):
                continue  # derivable aggregate, not a new fact
            value_cells = cells[1:]
        elif len(cells) == 5:
            stream_label = _cell_text(cells[1])
            if not stream_label:
                skipped += 1
                continue
            label = stream_label
            value_cells = cells[2:]
        else:
            skipped += 1
            continue

        if len(value_cells) != len(years):
            skipped += 1
            continue
        for year, cell in zip(years, value_cells):
            places = _parse_places(_cell_text(cell))
            if places is None:
                skipped += 1
                continue
            rows.append(AllocationRow(program_year=year, stream_name=label, places=places))

    if not rows:
        raise HiddenFieldError(
            "planning-levels page decoded but yielded zero rows - possible "
            "page redesign"
        )

    logger.info(
        "program_allocation: %d rows across %d streams and %d years (%d skipped)",
        len(rows), len({r.stream_name for r in rows}), len(years), skipped,
    )
    return ParseResult(rows=rows, skipped=skipped)
