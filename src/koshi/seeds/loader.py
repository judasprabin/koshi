import datetime as dt
import logging
from pathlib import Path
from typing import Any, Callable

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.models.ceiling_usage import CeilingUsage
from koshi.models.eligibility_requirements import EligibilityRequirement
from koshi.provenance import require_provenance
from koshi.resilience import isolated_item

_VALID_REQUIREMENT_TYPES = {"health", "character", "english_language"}

logger = logging.getLogger(__name__)


def load_seed_rows(path: Path, *, row_builder: Callable[[dict], Any]) -> tuple[list, int]:
    """Load entries from a YAML seed file, building one row per entry via
    row_builder. A bad entry (missing key, bad value, failed provenance or
    data-shape validation) is logged and skipped rather than aborting
    every other valid entry in the same file — a curation typo on one
    occupation shouldn't block the rest of the seed.
    """
    entries = yaml.safe_load(path.read_text())
    rows = []
    skipped = 0
    # entries or [] guards an empty/comment-only YAML file: yaml.safe_load
    # returns None in that case, and enumerate(None) raises TypeError
    # before the per-entry handler below ever gets a chance to run.
    for index, entry in enumerate(entries or []):
        try:
            rows.append(row_builder(entry))
        except Exception as exc:
            # Deliberately broad: this is a soft-fail boundary (skip one
            # entry, keep going), and row_builder can raise more than just
            # KeyError/ValueError — e.g. a quoted-string curation typo like
            # `issued: "3200"` makes the `ceiling <= 0`/`issued > ceiling`
            # comparisons raise TypeError. Catching narrowly here would let
            # that TypeError escape and abort the whole file, contradicting
            # this function's own promise that one bad entry shouldn't
            # block the rest of the seed.
            logger.warning("skipping seed entry %d in %s: %r", index, path.name, exc)
            skipped += 1
    return rows, skipped


def _build_ceiling_usage_row(entry: dict) -> CeilingUsage:
    retrieved_at = dt.datetime.fromisoformat(entry["retrieved_at"])
    require_provenance(
        reliability_tier="official_curated",
        source_url=entry["source_url"],
        retrieved_at=retrieved_at,
    )

    # Data-shape sanity, mirrored by the DB-level
    # ck_ceiling_usage_issued_within_ceiling CHECK constraint — fail fast
    # here with a clear error instead of relying on the DB round-trip.
    issued = entry["issued"]
    ceiling = entry["ceiling"]
    if ceiling <= 0:
        raise ValueError(f"{entry['occupation_code']!r}: ceiling must be > 0, got {ceiling!r}")
    if issued > ceiling:
        raise ValueError(
            f"{entry['occupation_code']!r}: issued ({issued}) exceeds ceiling ({ceiling})"
        )

    return CeilingUsage(
        occupation_code=entry["occupation_code"],
        program_year=entry["program_year"],
        issued=issued,
        ceiling=ceiling,
        as_of_date=dt.date.fromisoformat(entry["as_of_date"]),
        source_url=entry["source_url"],
        retrieved_at=retrieved_at,
        reliability_tier="official_curated",
    )


def load_ceiling_usage_seed(path: Path) -> list[CeilingUsage]:
    """Thin wrapper over load_seed_rows — preserves the original
    signature every existing caller/test uses."""
    rows, _skipped = load_seed_rows(path, row_builder=_build_ceiling_usage_row)
    return rows


def seed_ceiling_usage(session: Session, path: Path) -> list[CeilingUsage]:
    """Load the ceiling_usage seed file and persist any rows not already
    in the database.

    Upserts by (occupation_code, program_year, as_of_date) so re-running
    the seed doesn't manufacture duplicate rows. Each row's persistence is
    scoped in isolated_item — a DB-level failure (e.g. an unresolvable FK)
    on one row must not prevent other valid rows in the same file from
    landing.
    """
    rows = load_ceiling_usage_seed(path)

    new_rows = []
    for row in rows:
        with isolated_item(session, f"ceiling_usage seed for {row.occupation_code}"):
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
        # isolated_item's SAVEPOINT commit (or rollback, on a DB-level
        # failure such as an unresolvable FK) only happens on exit from
        # the `with` block above, so success can only be checked here —
        # a row that failed to flush never got its id assigned.
        if row.id is not None:
            new_rows.append(row)
    session.commit()
    return new_rows


def _build_eligibility_requirement_row(entry: dict) -> EligibilityRequirement:
    retrieved_at = dt.datetime.fromisoformat(entry["retrieved_at"])
    require_provenance(
        reliability_tier="official_curated",
        source_url=entry["source_url"],
        retrieved_at=retrieved_at,
    )

    # Mirrors the DB-level ck_eligibility_requirements_type CHECK
    # constraint — fail fast here with a clear error rather than relying
    # on the DB round-trip, matching ceiling_usage's issued/ceiling check.
    requirement_type = entry["requirement_type"]
    if requirement_type not in _VALID_REQUIREMENT_TYPES:
        raise ValueError(
            f"requirement_type must be one of {sorted(_VALID_REQUIREMENT_TYPES)}, "
            f"got {requirement_type!r}"
        )

    return EligibilityRequirement(
        requirement_type=requirement_type,
        summary=entry["summary"],
        source_url=entry["source_url"],
        retrieved_at=retrieved_at,
        reliability_tier="official_curated",
    )


def load_eligibility_requirements_seed(path: Path) -> list[EligibilityRequirement]:
    """Thin wrapper over load_seed_rows — preserves the original
    signature every existing caller/test uses."""
    rows, _skipped = load_seed_rows(path, row_builder=_build_eligibility_requirement_row)
    return rows


def seed_eligibility_requirements(session: Session, path: Path) -> list[EligibilityRequirement]:
    """Load the eligibility_requirements seed file and persist any new or
    changed rows.

    Upserts by requirement_type: unlike ceiling_usage's per-snapshot
    history, this is a single current summary per requirement, so a
    revised summary on re-run must update the existing row rather than
    accumulate a second one for the same type.
    """
    rows = load_eligibility_requirements_seed(path)

    changed_rows = []
    for row in rows:
        changed = False
        with isolated_item(session, f"eligibility_requirements seed for {row.requirement_type}"):
            existing = session.scalar(
                select(EligibilityRequirement).where(
                    EligibilityRequirement.requirement_type == row.requirement_type
                )
            )
            if existing is None:
                session.add(row)
                session.flush()  # populate row.id, mirroring ceiling_usage's success check
                changed = True
            elif existing.summary != row.summary or existing.source_url != row.source_url:
                existing.summary = row.summary
                existing.source_url = row.source_url
                existing.retrieved_at = row.retrieved_at
                changed = True
        # isolated_item's SAVEPOINT commit (or rollback, on a DB-level
        # failure) only happens on exit from the `with` block above, so
        # success can only be checked here — see seed_ceiling_usage's
        # identical row.id check for why this can't move inside the block.
        if changed:
            if existing is None:
                if row.id is not None:
                    changed_rows.append(row)
            else:
                changed_rows.append(existing)
    session.commit()
    return changed_rows
