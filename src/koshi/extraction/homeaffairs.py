"""Shared decoder for immi.homeaffairs.gov.au pages.

Every Home Affairs page in koshi's catalog (invitation rounds, planning
levels, fees, points, visa listings, English requirements, processing
times, previous rounds) serves its content the same way: the raw HTML
contains **zero `<table>` tags**, and the real content is HTML-entity-encoded
JSON in a single hidden input.

    <input id="ctl00_PlaceHolderMain_PageSchemaHiddenField_Input" value="...">

Decoding is `html.unescape` then `json.loads`; the payload is an object with
one root key whose value is a list of blocks, each carrying an HTML string.

The root key is **not uniform across the site** - main pages use `content`,
`previous-rounds` uses `criteria` - so callers must pass it explicitly and it
is stored per resource in `extraction_strategies.config`. Guessing wrong
raises rather than returning an empty result, because a parser that silently
extracts zero rows is exactly the failure this module exists to end.
"""

import html as html_module
import json
import logging
import re

from bs4 import BeautifulSoup
from bs4.element import Tag

logger = logging.getLogger(__name__)

HIDDEN_FIELD_ID = "ctl00_PlaceHolderMain_PageSchemaHiddenField_Input"

# The value attribute is entity-encoded, so it cannot itself contain a raw
# double quote - matching to the next quote is safe.
_HIDDEN_FIELD_RE = re.compile(
    rf'id="{re.escape(HIDDEN_FIELD_ID)}"[^>]*\svalue="([^"]*)"'
)

# Soft-404 markers: budget.gov.au serves HTTP 200 with a "Page not found"
# body, so status codes alone do not establish that a page still exists.
_SOFT_404_MARKERS = ("page not found", "page cannot be found", "404 error")


class HiddenFieldError(ValueError):
    """The page did not yield the expected hidden-field JSON structure.

    Raised in preference to returning an empty result: a page redesign must
    surface as a loud failure, not as a run that reports success with zero
    rows.
    """


def assert_not_soft_404(page_html: str, *, url: str) -> None:
    """Raise if the page body looks like a not-found page despite a 2xx.

    `raise_for_status()` cannot catch this - the response really is 200.
    """
    head = page_html[:4000].lower()
    for marker in _SOFT_404_MARKERS:
        if marker in head:
            raise HiddenFieldError(
                f"{url} returned a soft-404 (2xx status, {marker!r} in body)"
            )


def _decode_payload(page_html: str) -> dict:
    """Extract and JSON-decode the hidden field's payload object."""
    match = _HIDDEN_FIELD_RE.search(page_html)
    if match is None:
        raise HiddenFieldError(
            f"hidden field {HIDDEN_FIELD_ID!r} not found - possible page redesign"
        )
    try:
        payload = json.loads(html_module.unescape(match.group(1)))
    except json.JSONDecodeError as exc:
        raise HiddenFieldError(f"hidden field is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HiddenFieldError(
            f"expected a JSON object at the hidden field, got {type(payload).__name__}"
        )
    return payload


def decode_hidden_field(
    page_html: str, *, root_key: str, block_key: str = "block"
) -> list[str]:
    """Decode a Home Affairs page into its list of HTML content blocks.

    Args:
        page_html: The raw page HTML as fetched.
        root_key: The JSON root key for this page - `content` for most
            pages, `criteria` for previous-rounds. Comes from the resource's
            extraction strategy config, never guessed.
        block_key: The per-item key holding the HTML. `content` items use
            `block`; `criteria` items use `description`. Two axes of
            variation on the same site, so both are configured rather than
            sniffed.

    Returns:
        The HTML string of each content block, in document order.

    Raises:
        HiddenFieldError: if the hidden field is missing, the payload is not
            valid JSON, or `root_key`/`block_key` are absent from it.
    """
    payload = _decode_payload(page_html)

    if root_key not in payload:
        raise HiddenFieldError(
            f"root key {root_key!r} absent from hidden field; page carries "
            f"{sorted(payload)!r}. Root keys differ per page - check this "
            f"resource's configured json_root_key."
        )

    items = payload[root_key]
    if not isinstance(items, list):
        raise HiddenFieldError(
            f"expected a list under {root_key!r}, got {type(items).__name__}"
        )

    blocks = [
        item[block_key] for item in items if isinstance(item, dict) and block_key in item
    ]
    if not blocks:
        present = sorted({k for item in items if isinstance(item, dict) for k in item})
        raise HiddenFieldError(
            f"no {block_key!r} values found under {root_key!r}; items carry "
            f"{present!r}. Item shape differs per page - check this resource's "
            f"configured block key."
        )
    return blocks


def decode_hidden_field_items(
    page_html: str, *, root_key: str
) -> list[dict]:
    """Decode to the raw item dicts rather than just their HTML.

    `previous-rounds` carries the round date on the item itself (`title`),
    which is more reliable than parsing it back out of the HTML - the
    heading's own `id` attribute is demonstrably stale on these pages
    (`id="invitations-issued-13062024"` above text reading "13 November
    2025").
    """
    blocks_payload = _decode_payload(page_html)
    if root_key not in blocks_payload:
        raise HiddenFieldError(
            f"root key {root_key!r} absent from hidden field; page carries "
            f"{sorted(blocks_payload)!r}"
        )
    items = blocks_payload[root_key]
    if not isinstance(items, list):
        raise HiddenFieldError(
            f"expected a list under {root_key!r}, got {type(items).__name__}"
        )
    return [item for item in items if isinstance(item, dict)]


def find_table_after_heading(block_html: str, *, heading_contains: str) -> Tag:
    """Return the first <table> following the heading matching a substring.

    Home Affairs tables carry no id or class, and one of them (the
    occupation/minimum-score table) has no <th> headers at all, so it cannot
    be located by header text. Its preceding heading is the only stable,
    semantic anchor - far more robust than a positional index, which shifts
    whenever a block gains a table.

    Comparison is case-insensitive, and non-breaking spaces are normalised
    (headings on these pages contain \\xa0).
    """
    soup = BeautifulSoup(block_html, "lxml")
    needle = heading_contains.replace("\xa0", " ").casefold()

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = heading.get_text(strip=True).replace("\xa0", " ").casefold()
        if needle in text:
            table = heading.find_next("table")
            if table is None:
                raise HiddenFieldError(
                    f"heading matching {heading_contains!r} has no following table"
                )
            return table

    raise HiddenFieldError(
        f"no heading matching {heading_contains!r} - possible page redesign"
    )


def assert_table_shape(
    table: Tag, *, expected_columns: int, min_rows: int, description: str
) -> list[Tag]:
    """Validate a table's shape before parsing it row by row, returning rows.

    This is the assertion the old SkillSelect parser lacked. It unpacked
    three cells from a two-column table, so every row raised ValueError, was
    caught by the per-row handler, and was skipped - a 100% skip rate that
    looked like 140 individual data-quality problems and exited cleanly.
    Shape is a property of the page, not of a row: when it is wrong, fail
    once and loudly instead of failing silently 140 times.
    """
    body = table.find("tbody")
    if body is None:
        raise HiddenFieldError(f"{description}: table has no tbody - possible redesign")

    rows = body.find_all("tr")
    if len(rows) < min_rows:
        raise HiddenFieldError(
            f"{description}: expected at least {min_rows} rows, found {len(rows)} "
            f"- possible page redesign or an emptied table"
        )

    widths = {len(row.find_all(["td", "th"])) for row in rows}
    if widths != {expected_columns}:
        raise HiddenFieldError(
            f"{description}: expected {expected_columns} columns, found widths "
            f"{sorted(widths)} - possible page redesign"
        )
    return rows
