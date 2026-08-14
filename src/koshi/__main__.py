"""Runnable entry point for koshi's full local sync.

Usage (after `alembic upgrade head`):

    python -m koshi

Runs, in order:
1. sync_anzsco_occupations — occupations must exist first: eoi_rounds and
   ceiling_usage rows both carry a FK to occupations.code.
2. sync_skillselect_rounds — persists new EOI rounds and (per pipeline.py)
   refreshes occupation_momentum for every occupation a new round touches.
3. seed_ceiling_usage — persists the manually-curated ceiling data shipped
   in seeds/ceiling_usage_manual.yaml (design spec §4/§5 tier 5: this data
   isn't scrapable, so it's curated and cited by hand instead).

Without step 3, GET /v1/occupations/{code} has no ceiling_usage row to key
off; without step 2 running as part of a normal sync, momentum stays null
forever. This is what makes the slice runnable end-to-end from a fresh
install, matching the README's "Local development" instructions.
"""

from pathlib import Path

from koshi.db import SessionLocal
from koshi.pipeline import sync_anzsco_occupations, sync_skillselect_rounds
from koshi.seeds.loader import seed_ceiling_usage

CEILING_USAGE_SEED_PATH = Path(__file__).parent / "seeds" / "ceiling_usage_manual.yaml"


def main() -> None:
    session = SessionLocal()
    try:
        occupations = sync_anzsco_occupations(session)
        print(f"anzsco_occupations: {len(occupations)} new/updated")

        new_rounds = sync_skillselect_rounds(session)
        print(f"skillselect_rounds: {len(new_rounds)} new rounds (momentum refreshed for each occupation touched)")

        new_ceiling_rows = seed_ceiling_usage(session, CEILING_USAGE_SEED_PATH)
        print(f"ceiling_usage: {len(new_ceiling_rows)} new rows seeded from {CEILING_USAGE_SEED_PATH.name}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
