import datetime as dt
import re

from bs4 import BeautifulSoup

from koshi.models.eoi_rounds import EoiRound
from koshi.provenance import require_provenance

ROUND_DATE_RE = re.compile(r"Round date:\s*(\d{1,2} \w+ \d{4})")


def parse_skillselect_rounds(
    html: str, *, visa_code: str, source_url: str, retrieved_at: dt.datetime
) -> list[EoiRound]:
    require_provenance(
        reliability_tier="official_scraped", source_url=source_url, retrieved_at=retrieved_at
    )

    soup = BeautifulSoup(html, "lxml")
    date_match = ROUND_DATE_RE.search(soup.get_text())
    if not date_match:
        raise ValueError("could not find round date in page")
    round_date = dt.datetime.strptime(date_match.group(1), "%d %B %Y").date()

    table = soup.find("table", id="round-results")
    rows = table.find("tbody").find_all("tr")

    results = []
    for row in rows:
        occupation_code, threshold, invitations = (
            c.get_text(strip=True) for c in row.find_all("td")
        )
        results.append(
            EoiRound(
                visa_code=visa_code,
                occupation_code=occupation_code,
                round_date=round_date,
                threshold_points=int(threshold),
                invitations_issued=int(invitations),
                source_url=source_url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
    return results
