import datetime as dt

from koshi.models.ceiling_usage import CeilingUsage


def test_insert_and_read_ceiling_usage(db_session):
    from koshi.models.occupations import Occupation

    db_session.add(
        Occupation(
            code="261313", name="Software Engineer", unit_group="2613",
            source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()

    row = CeilingUsage(
        occupation_code="261313",
        program_year="2025-26",
        issued=3200,
        ceiling=5000,
        as_of_date=dt.date(2026, 7, 31),
        source_url="https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels",
        retrieved_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
        reliability_tier="official_curated",
    )
    db_session.add(row)
    db_session.commit()

    found = db_session.query(CeilingUsage).filter_by(occupation_code="261313").one()
    assert found.issued == 3200
    assert found.ceiling == 5000
    assert found.reliability_tier == "official_curated"
