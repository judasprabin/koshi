import datetime as dt

from koshi.models.eoi_rounds import EoiRound


def test_insert_and_read_eoi_round(db_session):
    from koshi.models.occupations import Occupation

    db_session.add(
        Occupation(
            code="261313", name="Software Engineer", unit_group="2613",
            source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()

    round_row = EoiRound(
        visa_code="189",
        occupation_code="261313",
        occupation_name_raw="261313",
        round_date=dt.date(2026, 7, 24),
        threshold_points=85,
        invitations_issued=120,
        source_url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
        retrieved_at=dt.datetime(2026, 7, 25, tzinfo=dt.timezone.utc),
        reliability_tier="official_scraped",
    )
    db_session.add(round_row)
    db_session.commit()

    found = db_session.query(EoiRound).filter_by(occupation_code="261313").one()
    assert found.threshold_points == 85
    assert found.visa_code == "189"
