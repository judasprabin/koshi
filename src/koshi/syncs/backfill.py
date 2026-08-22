import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crosswalk import resolve_occupation_code
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupations import Occupation
from koshi.pipeline import refresh_momentum_for_codes

logger = logging.getLogger(__name__)


def backfill_unresolved_round_codes(session: Session) -> list[EoiRound]:
    """Retry code resolution for stored rounds that never resolved.

    Without this, a row unresolved once stays unresolved forever: the
    source page has not changed, so `_needs_extraction` returns False and
    the round is never revisited — even though the *crosswalk* may have
    grown since (a new source, a new edition, a normalisation fix).

    This is the case that actually bit: archived rounds naming
    `Cabinetmaker` were persisted before LIN 19/051's ANZSCO-2013-only
    occupations were loaded, so their FK target did not yet exist.

    Momentum is refreshed for anything newly resolved, since a round that
    only now has a code was not counted in any earlier trend.
    """
    pending = list(
        session.scalars(select(EoiRound).where(EoiRound.occupation_code.is_(None)))
    )
    if not pending:
        return []

    resolved = [r for r in pending if _apply_code(session, r)]
    session.commit()
    logger.info(
        "backfill: resolved %d of %d previously-unresolved round(s)",
        len(resolved), len(pending),
    )
    refresh_momentum_for_codes(session, {r.occupation_code for r in resolved})
    return resolved


def _apply_code(session: Session, round_: EoiRound) -> bool:
    """Resolve one round's code, honouring the occupations FK. Returns
    whether a code was written."""
    code = resolve_occupation_code(session, round_.occupation_name_raw)
    if code is None or session.get(Occupation, code) is None:
        return False
    round_.occupation_code = code
    return True
