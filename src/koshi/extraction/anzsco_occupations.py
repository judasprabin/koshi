"""Parser for the Jobs & Skills Australia ANZSCO occupation listing.

Rewritten 2026-08-18 against the live page. The previous implementation
looked for a `<table id="occupation-list">`; the page is a Drupal Views
card grid and contains no table markup at all, so the parser raised on
every run.

Verified card markup:

    <div class="rowc"><a href="...">
      <div class="card_inner">
        <div class="card_anzsco">ANZSCO 422111</div>
        <h4 class="card_title">Aboriginal and Torres Strait Islander ...</h4>

The listing paginates at 12 cards over 103 pages (1,236 results) via a
plain `?page=N` query string - no JS required, but it does mean a single
fetch yields 12 of 1,236 occupations.

Note JSA has superseded ANZSCO in favour of OSCA and no longer updates it.
koshi keeps ANZSCO as its occupation key because the binding legislative
instrument (LIN 19/051) and every state list are ANZSCO-coded; see the data
model's C19 crosswalk.
"""

import dataclasses
import datetime as dt
import logging
import re

from bs4 import BeautifulSoup

from koshi.models.occupations import Occupation
from koshi.provenance import require_provenance

logger = logging.getLogger(__name__)

# JSA publishes the 2022 edition (alongside OSCA, which koshi does not use).
ANZSCO_EDITION = "2022"

CARD_CONTAINER_SELECTOR = "div.view-occupation-index"
CARD_SELECTOR = "div.rowc"

_DIGITS_RE = re.compile(r"\d+")
_PAGE_LINK_RE = re.compile(r"\?page=(\d+)")


class AnzscoPageError(ValueError):
    """The ANZSCO listing did not have the expected card structure.

    Raised rather than returning an empty result: a redesign must fail
    loudly, not look like a page with no occupations on it.
    """


@dataclasses.dataclass
class ParseResult:
    rows: list[Occupation]
    skipped: int


def has_next_page(page_html: str, *, current_page: int) -> bool:
    """Whether the pager advertises a page after `current_page`.

    The pager lists every page number as a `?page=N` link, so the highest N
    present is the last page. Reading it beats guessing from card counts,
    which breaks on a short final page.
    """
    pages = [int(m) for m in _PAGE_LINK_RE.findall(page_html)]
    return bool(pages) and max(pages) > current_page


def _parse_card(card, *, source_url: str, retrieved_at: dt.datetime) -> Occupation:
    code_el = card.select_one("div.card_anzsco")
    title_el = card.select_one("h4.card_title")
    if code_el is None or title_el is None:
        raise ValueError("card is missing its code or title element")

    # Rendered as "ANZSCO 422111" (and "OSCA 432931" on the sibling OSCA
    # listing), so take the digits rather than splitting on a fixed prefix.
    match = _DIGITS_RE.search(code_el.get_text(strip=True))
    if match is None:
        raise ValueError(f"no numeric code in {code_el.get_text(strip=True)!r}")
    code = match.group()

    name = title_el.get_text(strip=True)
    if not name:
        raise ValueError(f"card {code} has an empty title")

    # The listing interleaves 4-digit unit groups with 6-digit occupations.
    # Recording which is which keeps joins honest: sources disagree on the
    # width they key by (NSW joins at 4-digit, QLD and LIN 19/051 at
    # 6-digit), and without this marker the two are indistinguishable.
    if len(code) == 4:
        code_grain = "unit_group"
    elif len(code) == 6:
        code_grain = "occupation"
    else:
        raise ValueError(f"unexpected ANZSCO code width: {code!r}")

    return Occupation(
        code=code,
        name=name,
        unit_group=code[:4],
        code_grain=code_grain,
        anzsco_edition=ANZSCO_EDITION,
        source_url=source_url,
        retrieved_at=retrieved_at,
        reliability_tier="official_scraped",
    )


def parse_anzsco_occupations(
    page_html: str, *, source_url: str, retrieved_at: dt.datetime
) -> ParseResult:
    """Extract one Occupation per card from a single ANZSCO listing page.

    Raises:
        AnzscoPageError: if the page has no occupation cards at all, which
            means a redesign rather than an empty result set.
    """
    require_provenance(
        reliability_tier="official_scraped", source_url=source_url, retrieved_at=retrieved_at
    )

    soup = BeautifulSoup(page_html, "lxml")
    container = soup.select_one(CARD_CONTAINER_SELECTOR)
    cards = (container or soup).select(CARD_SELECTOR)
    if not cards:
        raise AnzscoPageError(
            f"no occupation cards found ({CARD_SELECTOR!r} within "
            f"{CARD_CONTAINER_SELECTOR!r}) - possible page redesign"
        )

    occupations: list[Occupation] = []
    skipped = 0
    for index, card in enumerate(cards):
        try:
            occupations.append(
                _parse_card(card, source_url=source_url, retrieved_at=retrieved_at)
            )
        except ValueError as exc:
            logger.warning("skipping ANZSCO card %d: %s", index, exc)
            skipped += 1

    return ParseResult(rows=occupations, skipped=skipped)
