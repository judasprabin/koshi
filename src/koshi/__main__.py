"""Runnable entry point for koshi's full local sync.

Usage (after `alembic upgrade head`):

    python -m koshi

Runs, in order:
1. sync_anzsco_occupations — occupations must exist first: eoi_rounds and
   ceiling_usage rows both carry a FK to occupations.code.
2. sync_abs_occupations — merges the ABS classification's full occupation
   set. JSA's browse listing surfaces only 878 of ANZSCO's 1,076 six-digit
   occupations, and rounds referencing the remainder cannot be linked.
3. sync_occupation_titles — loads the name->code crosswalk from LIN 19/051
   and the ABS ANZSCO workbook. Must precede the rounds sync: SkillSelect
   publishes occupation names, never codes, so without the crosswalk every
   round lands with a NULL occupation_code and no momentum is computed.
4. sync_skillselect_rounds — persists new EOI rounds, resolves each one's
   occupation_code via the crosswalk, and (per pipeline.py) refreshes
   occupation_momentum for every occupation a new round touches.
5. sync_skillselect_previous_rounds — backfills historical rounds. Momentum
   needs a trailing window of three rounds and the current-round page
   publishes one, so without this every occupation's trend is null.
6. backfill_unresolved_round_codes — retries code resolution for stored
   rounds that never resolved. The crosswalk grows independently of the
   source pages, and an unchanged page is never re-parsed, so without
   this a row unresolved once stays unresolved forever.
7. seed_ceiling_usage — persists any manually-curated ceiling data in
   seeds/ceiling_usage_manual.yaml. That file is currently empty by design:
   per-occupation ceilings are not published anywhere at koshi's grain.

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
from koshi.pipeline import (
    backfill_unresolved_round_codes,
    sync_abs_occupations,
    sync_anzsco_occupations,
    sync_occupation_titles,
    sync_skillselect_previous_rounds,
    sync_skillselect_rounds,
)
from koshi.run_summary import write_run_summary
from koshi.seeds.loader import seed_ceiling_usage

CEILING_USAGE_SEED_PATH = Path(__file__).parent / "seeds" / "ceiling_usage_manual.yaml"


def main() -> int:
    setup_logging()
    # Deliberately NOT logging.getLogger(__name__): __name__ resolves to
    # "koshi.__main__" when this module is imported normally (as in
    # tests), but to the bare string "__main__" when actually executed
    # via `python -m koshi` (runpy sets __name__ == "__main__" for the
    # script being run). An explicit string keeps the logger name — and
    # therefore per-logger filtering/level configuration — stable
    # regardless of how the module is invoked.
    logger = logging.getLogger("koshi.__main__")
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
        ("abs_occupations", lambda: sync_abs_occupations(session)),
        ("occupation_titles", lambda: sync_occupation_titles(session)),
        ("skillselect_rounds", lambda: sync_skillselect_rounds(session)),
        ("skillselect_previous_rounds", lambda: sync_skillselect_previous_rounds(session)),
        ("backfill_round_codes", lambda: backfill_unresolved_round_codes(session)),
        ("ceiling_usage_seed", lambda: seed_ceiling_usage(session, CEILING_USAGE_SEED_PATH)),
    ]

    try:
        for name, step in steps:
            try:
                result = step()
                step_summary = {"name": name, "status": "ok", "count": len(result)}
                # sync_anzsco_occupations/sync_skillselect_rounds surface
                # their extraction parser's skip count via a bonus
                # `.skipped` attribute on the returned list (see
                # pipeline._RowsWithSkipCount) rather than a return-type
                # change — a run that silently drops most rows to
                # soft-fails should still be visible here even though it
                # reports "status": "ok".
                skipped = getattr(result, "skipped", None)
                if skipped is not None:
                    step_summary["skipped"] = skipped
                summary["steps"].append(step_summary)
                logger.info("%s: %d new/updated", name, len(result))
            except Exception as exc:
                session.rollback()
                logger.exception("%s failed — continuing with remaining steps", name)
                summary["steps"].append({
                    "name": name,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                })
    finally:
        session.close()

    ok = sum(1 for s in summary["steps"] if s["status"] == "ok")
    failed = sum(1 for s in summary["steps"] if s["status"] == "failed")
    if failed and ok == 0:
        exit_code = 3
    elif failed:
        exit_code = 2
    else:
        exit_code = 0

    summary["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    summary["exit_code"] = exit_code

    write_run_summary(summary)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
