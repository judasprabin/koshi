import datetime as dt

from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupation_momentum import OccupationMomentum
from koshi.models.occupations import Occupation
from koshi.momentum import compute_momentum, refresh_momentum


def _seed_occupation(db_session, code="261313"):
    db_session.add(
        Occupation(
            code=code, name="Software Engineer", unit_group="2613",
            source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()


def _seed_rounds(db_session, code, thresholds):
    base_date = dt.date(2026, 5, 1)
    for i, points in enumerate(thresholds):
        db_session.add(
            EoiRound(
                visa_code="189",
                occupation_code=code,
                round_date=base_date + dt.timedelta(days=30 * i),
                threshold_points=points,
                invitations_issued=100,
                source_url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
                retrieved_at=dt.datetime.now(dt.timezone.utc),
                reliability_tier="official_scraped",
            )
        )
    db_session.commit()


def test_compute_momentum_rising_when_threshold_increases(db_session):
    _seed_occupation(db_session)
    _seed_rounds(db_session, "261313", thresholds=[70, 75, 85])  # oldest -> newest

    assert compute_momentum(db_session, "261313") == "rising"


def test_compute_momentum_falling_when_threshold_decreases(db_session):
    _seed_occupation(db_session)
    _seed_rounds(db_session, "261313", thresholds=[85, 80, 70])

    assert compute_momentum(db_session, "261313") == "falling"


def test_compute_momentum_none_with_fewer_than_three_rounds(db_session):
    _seed_occupation(db_session)
    _seed_rounds(db_session, "261313", thresholds=[70, 75])

    assert compute_momentum(db_session, "261313") is None


def test_refresh_momentum_persists_a_derived_row(db_session):
    _seed_occupation(db_session)
    _seed_rounds(db_session, "261313", thresholds=[70, 75, 85])

    refresh_momentum(db_session, "261313")

    row = db_session.query(OccupationMomentum).filter_by(occupation_code="261313").one()
    assert row.direction == "rising"
    assert row.reliability_tier == "derived"
