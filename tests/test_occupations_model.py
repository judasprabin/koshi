import datetime as dt

from koshi.models.occupations import Occupation


def test_insert_and_read_occupation(db_session):
    occupation = Occupation(
        code="261313",
        name="Software Engineer",
        unit_group="2613 Software and Applications Programmers",
        source_url="https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco",
        retrieved_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
        reliability_tier="official_scraped",
    )
    db_session.add(occupation)
    db_session.commit()

    found = db_session.get(Occupation, "261313")
    assert found.name == "Software Engineer"
    assert found.reliability_tier == "official_scraped"
