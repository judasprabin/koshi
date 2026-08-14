import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupation_momentum import OccupationMomentum


def compute_momentum(session: Session, occupation_code: str) -> str | None:
    """Trailing 3-round threshold delta. Computed from koshi's own
    eoi_rounds rows — never scraped (design spec §3.3)."""
    rounds = session.scalars(
        select(EoiRound)
        .where(EoiRound.occupation_code == occupation_code)
        .order_by(EoiRound.round_date.desc())
        .limit(3)
    ).all()
    if len(rounds) < 3:
        return None

    newest, _mid, oldest = rounds
    delta = newest.threshold_points - oldest.threshold_points
    if delta > 0:
        return "rising"
    if delta < 0:
        return "falling"
    return "steady"


def refresh_momentum(session: Session, occupation_code: str) -> None:
    direction = compute_momentum(session, occupation_code)
    if direction is None:
        return
    session.add(
        OccupationMomentum(
            occupation_code=occupation_code,
            computed_at=dt.datetime.now(dt.timezone.utc),
            direction=direction,
            reliability_tier="derived",
        )
    )
    session.commit()
