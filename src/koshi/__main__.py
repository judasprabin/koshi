"""Runnable entry point for koshi's full local sync.

Usage (after `alembic upgrade head`):

    python -m koshi

Runs, in order:
1. sync_anzsco_occupations — occupations must exist first: eoi_rounds and
   ceiling_usage rows both carry a FK to occupations.code.
2. sync_skillselect_rounds — persists new EOI rounds and (per pipeline.py)
   refreshes occupation_momentum for every occupation a new round touches.
3. seed_ceiling_usage — persists the manually-curated ceiling data shipped
   in seeds/ceiling_usage_manual.yaml.

Each step is isolated: a failure in one is logged and recorded in the run
summary, but does NOT prevent the remaining steps from running — e.g.
seed_ceiling_usage has zero dependency on either scraping step succeeding
and must still run even if both of them fail.

Exit codes: 0 clean, 1 fatal init failure (session construction or the
liveness check below fails — e.g. an unreachable database — before any
step runs), 2 partial failure (some steps ok, some failed — the expected common state
once there are many sources, not a rare edge case), 3 total failure (every
step failed). A cron wrapper (and later, Cloud Scheduler + Cloud
Monitoring) can act on 2/3 without koshi needing any notification
integration built — see the ETL finalization design doc §8.
"""
import logging
import sys
import datetime as dt
from pathlib import Path

from sqlalchemy import text

from koshi.db import SessionLocal
from koshi.logging_config import setup_logging
from koshi.pipeline import sync_anzsco_occupations, sync_skillselect_rounds
from koshi.run_summary import write_run_summary
from koshi.seeds.loader import seed_ceiling_usage

CEILING_USAGE_SEED_PATH = Path(__file__).parent / "seeds" / "ceiling_usage_manual.yaml"


def main() -> int:
    setup_logging()
    logger = logging.getLogger(__name__)
    try:
        session = SessionLocal()
        # sessionmaker()'s call above only constructs a Session object — it
        # does NOT open a connection (SQLAlchemy connects lazily on first
        # use). Without this liveness check, an unreachable database would
        # sail past this except block and only surface inside step 1's own
        # try/except below, yielding exit code 3 (partial/total failure)
        # instead of the fatal-init code 1 this block exists to report.
        session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("fatal: could not initialize a database session")
        return 1

    summary: dict = {
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "steps": [],
    }

    steps = [
        ("anzsco_occupations", lambda: sync_anzsco_occupations(session)),
        ("skillselect_rounds", lambda: sync_skillselect_rounds(session)),
        ("ceiling_usage_seed", lambda: seed_ceiling_usage(session, CEILING_USAGE_SEED_PATH)),
    ]

    try:
        for name, step in steps:
            try:
                result = step()
                summary["steps"].append({"name": name, "status": "ok", "count": len(result)})
                logger.info("%s: %d new/updated", name, len(result))
            except Exception:
                session.rollback()
                logger.exception("%s failed — continuing with remaining steps", name)
                summary["steps"].append({"name": name, "status": "failed"})
    finally:
        session.close()

    write_run_summary(summary)

    ok = sum(1 for s in summary["steps"] if s["status"] == "ok")
    failed = sum(1 for s in summary["steps"] if s["status"] == "failed")
    if failed and ok == 0:
        return 3
    if failed:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
