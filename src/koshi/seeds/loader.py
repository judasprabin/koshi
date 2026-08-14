import datetime as dt
from pathlib import Path

import yaml

from koshi.models.ceiling_usage import CeilingUsage
from koshi.provenance import require_provenance


def load_ceiling_usage_seed(path: Path) -> list[CeilingUsage]:
    entries = yaml.safe_load(path.read_text())
    rows = []
    for entry in entries:
        require_provenance(reliability_tier="official_curated", source_url=entry["source_url"])
        rows.append(
            CeilingUsage(
                occupation_code=entry["occupation_code"],
                program_year=entry["program_year"],
                issued=entry["issued"],
                ceiling=entry["ceiling"],
                as_of_date=dt.date.fromisoformat(entry["as_of_date"]),
                source_url=entry["source_url"],
                retrieved_at=dt.datetime.fromisoformat(entry["retrieved_at"]),
                reliability_tier="official_curated",
            )
        )
    return rows
