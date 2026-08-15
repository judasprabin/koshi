import dataclasses
import datetime as dt
import logging

from bs4 import BeautifulSoup

from koshi.models.occupations import Occupation
from koshi.provenance import require_provenance

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ParseResult:
    rows: list[Occupation]
    skipped: int


def parse_anzsco_occupations(
    html: str, *, source_url: str, retrieved_at: dt.datetime
) -> ParseResult:
    require_provenance(
        reliability_tier="official_scraped", source_url=source_url, retrieved_at=retrieved_at
    )

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="occupation-list")
    if table is None:
        raise ValueError("occupation-list table not found — possible page redesign")
    tbody = table.find("tbody")
    if tbody is None:
        raise ValueError("occupation-list table has no tbody — possible page redesign")
    rows = tbody.find_all("tr")

    occupations: list[Occupation] = []
    skipped = 0
    for index, row in enumerate(rows):
        cells = row.find_all("td")
        try:
            code, name, unit_group = (c.get_text(strip=True) for c in cells)
        except ValueError as exc:
            logger.warning(
                "skipping ANZSCO row %d: %r (cell texts=%r)",
                index, exc, [c.get_text(strip=True) for c in cells],
            )
            skipped += 1
            continue

        occupations.append(
            Occupation(
                code=code,
                name=name,
                unit_group=unit_group,
                source_url=source_url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
    return ParseResult(rows=occupations, skipped=skipped)
