"""Parser for the SkillSelect points-test criteria page (data model C10).

The catalogued URL (`/points-tested`) genuinely contains no points table —
not a JS-rendering problem, just the wrong page. The real table lives at
the sibling `/points-table`, decoded the same way every other Home Affairs
page is: hidden-field JSON, root key `content`, one item per criterion
category ("Age", "English language skills", ...), each carrying an HTML
`block` with zero, one, or two embedded `<table>` elements.

Two shapes worth naming explicitly:

- Most items carry exactly one table — its criterion_name is the item's
  own `text` (e.g. "Age").
- "Skilled employment experience" carries **two** tables (overseas /
  Australian), disambiguated only by an `<h3>` immediately preceding each
  — there is no other signal that separates them, so criterion_name
  becomes `"<item text> — <h3 text>"` for any block with more than one
  table.

"Overview" (id -1, prose only, no table) is skipped, not an error — a page
this size legitimately has narrative sections alongside criterion tables.
"""

import dataclasses
import logging

from bs4 import BeautifulSoup

from koshi.extraction.homeaffairs import HiddenFieldError, decode_hidden_field_items

logger = logging.getLogger(__name__)

DEFAULT_ROOT_KEY = "content"


@dataclasses.dataclass
class CriterionRow:
    criterion_name: str
    band_description: str
    points_value: int


@dataclasses.dataclass
class ParseResult:
    rows: list[CriterionRow]
    skipped: int


def parse_points_criteria(
    page_html: str, *, root_key: str = DEFAULT_ROOT_KEY
) -> ParseResult:
    items = decode_hidden_field_items(page_html, root_key=root_key)

    rows: list[CriterionRow] = []
    skipped = 0

    for item in items:
        block_html = item.get("block")
        label = item.get("text")
        if not block_html or not label:
            continue
        label = label.strip()

        soup = BeautifulSoup(block_html, "lxml")
        tables = soup.find_all("table")
        if not tables:
            # e.g. "Overview" — narrative content, no criterion table.
            continue

        for index, table in enumerate(tables):
            criterion_name = _criterion_name(label, table, index=index, multi=len(tables) > 1)
            body = table.find("tbody")
            if body is None:
                skipped += 1
                continue
            for tr in body.find_all("tr"):
                cells = tr.find_all("td")
                if len(cells) != 2:
                    skipped += 1
                    continue
                band = cells[0].get_text(strip=True).replace("\xa0", " ")
                points_text = cells[1].get_text(strip=True)
                try:
                    points_value = int(points_text)
                except ValueError:
                    skipped += 1
                    continue
                rows.append(
                    CriterionRow(
                        criterion_name=criterion_name,
                        band_description=band,
                        points_value=points_value,
                    )
                )

    if not rows:
        raise HiddenFieldError(
            "points-criteria page decoded but yielded zero table rows - "
            "possible page redesign"
        )

    logger.info(
        "points_criteria: parsed %d rows across %d criteria (%d skipped)",
        len(rows), len({r.criterion_name for r in rows}), skipped,
    )
    return ParseResult(rows=rows, skipped=skipped)


def _criterion_name(label: str, table, *, index: int, multi: bool) -> str:
    if not multi:
        return label
    heading = table.find_previous(["h2", "h3", "h4"])
    if heading is not None:
        sub = heading.get_text(strip=True).replace("\xa0", " ")
        return f"{label} — {sub}"
    return f"{label} (table {index + 1})"
