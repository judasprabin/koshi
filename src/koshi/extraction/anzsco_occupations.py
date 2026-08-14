import datetime as dt

from bs4 import BeautifulSoup

from koshi.models.occupations import Occupation
from koshi.provenance import require_provenance


def parse_anzsco_occupations(
    html: str, *, source_url: str, retrieved_at: dt.datetime
) -> list[Occupation]:
    require_provenance(reliability_tier="official_scraped", source_url=source_url)

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="occupation-list")
    rows = table.find("tbody").find_all("tr")

    occupations = []
    for row in rows:
        code, name, unit_group = (c.get_text(strip=True) for c in row.find_all("td"))
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
    return occupations
