import dataclasses
import datetime as dt
import logging
import re

from bs4 import BeautifulSoup

from koshi.models.eoi_rounds import EoiRound
from koshi.provenance import require_provenance
from koshi.resilience import parse_int_loose

logger = logging.getLogger(__name__)

ROUND_DATE_RE = re.compile(r"Round date:\s*(\d{1,2} \w+ \d{4})")


@dataclasses.dataclass
class ParseResult:
    rows: list[EoiRound]
    skipped: int


def parse_skillselect_rounds(
    html: str, *, visa_code: str, source_url: str, retrieved_at: dt.datetime
) -> ParseResult:
    require_provenance(
        reliability_tier="official_scraped", source_url=source_url, retrieved_at=retrieved_at
    )

    soup = BeautifulSoup(html, "lxml")
    date_match = ROUND_DATE_RE.search(soup.get_text())
    if not date_match:
        raise ValueError("could not find round date in page")
    round_date = dt.datetime.strptime(date_match.group(1), "%d %B %Y").date()

    table = soup.find("table", id="round-results")
    if table is None:
        raise ValueError("round-results table not found — possible page redesign")
    tbody = table.find("tbody")
    if tbody is None:
        raise ValueError("round-results table has no tbody — possible page redesign")
    rows = tbody.find_all("tr")

    results: list[EoiRound] = []
    skipped = 0
    for index, row in enumerate(rows):
        cells = row.find_all("td")
        try:
            occupation_code, threshold_text, invitations_text = (
                c.get_text(strip=True) for c in cells
            )
            threshold_points = parse_int_loose(threshold_text)
            if threshold_points is None:
                raise ValueError(f"threshold_points is required, got {threshold_text!r}")
            invitations_issued = parse_int_loose(invitations_text)
        except ValueError as exc:
            logger.warning(
                "skipping SkillSelect row %d: %r (cell texts=%r)",
                index, exc, [c.get_text(strip=True) for c in cells],
            )
            skipped += 1
            continue

        results.append(
            EoiRound(
                visa_code=visa_code,
                occupation_code=occupation_code,
                round_date=round_date,
                threshold_points=threshold_points,
                invitations_issued=invitations_issued,
                source_url=source_url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
    return ParseResult(rows=results, skipped=skipped)
