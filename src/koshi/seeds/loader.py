import datetime as dt
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.models.ceiling_usage import CeilingUsage
from koshi.provenance import require_provenance


def load_ceiling_usage_seed(path: Path) -> list[CeilingUsage]:
    entries = yaml.safe_load(path.read_text())
    rows = []
    for entry in entries:
        retrieved_at = dt.datetime.fromisoformat(entry["retrieved_at"])
        require_provenance(
            reliability_tier="official_curated",
            source_url=entry["source_url"],
            retrieved_at=retrieved_at,
        )

        # Data-shape sanity, mirrored by the DB-level
        # ck_ceiling_usage_issued_within_ceiling CHECK constraint (migration
        # 0006) — fail fast here with a clear error instead of relying on
        # the DB round-trip, and instead of generate_ceiling_insight later
        # hitting a ZeroDivisionError or reporting an impossible >100% used.
        issued = entry["issued"]
        ceiling = entry["ceiling"]
        if ceiling <= 0:
            raise ValueError(
                f"{entry['occupation_code']!r}: ceiling must be > 0, got {ceiling!r}"
            )
        if issued > ceiling:
            raise ValueError(
                f"{entry['occupation_code']!r}: issued ({issued}) exceeds ceiling ({ceiling})"
            )

        rows.append(
            CeilingUsage(
                occupation_code=entry["occupation_code"],
                program_year=entry["program_year"],
                issued=issued,
                ceiling=ceiling,
                as_of_date=dt.date.fromisoformat(entry["as_of_date"]),
                source_url=entry["source_url"],
                retrieved_at=retrieved_at,
                reliability_tier="official_curated",
            )
        )
    return rows


def seed_ceiling_usage(session: Session, path: Path) -> list[CeilingUsage]:
    """Load the ceiling_usage seed file and persist any rows not already
    in the database.

    Upserts by (occupation_code, program_year, as_of_date) — the same
    existing-row-check pattern sync_skillselect_rounds (pipeline.py) uses
    for eoi_rounds — so re-running the seed (e.g. every `python -m koshi`
    invocation) doesn't manufacture duplicate rows.
    """
    rows = load_ceiling_usage_seed(path)

    new_rows = []
    for row in rows:
        existing = session.scalar(
            select(CeilingUsage).where(
                CeilingUsage.occupation_code == row.occupation_code,
                CeilingUsage.program_year == row.program_year,
                CeilingUsage.as_of_date == row.as_of_date,
            )
        )
        if existing is not None:
            continue
        session.add(row)
        new_rows.append(row)
    session.commit()
    return new_rows
