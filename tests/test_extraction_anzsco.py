import datetime as dt
from pathlib import Path

from koshi.extraction.anzsco_occupations import parse_anzsco_occupations

FIXTURE = (Path(__file__).parent / "fixtures" / "anzsco_sample.html").read_text()
SOURCE_URL = "https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco"
RETRIEVED_AT = dt.datetime(2026, 8, 14, tzinfo=dt.timezone.utc)


def test_parses_two_occupations_from_fixture():
    result = parse_anzsco_occupations(FIXTURE, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT)

    assert len(result) == 2
    swe = next(o for o in result if o.code == "261313")
    assert swe.name == "Software Engineer"
    assert swe.unit_group == "2613 Software and Applications Programmers"
    assert swe.reliability_tier == "official_scraped"
    assert swe.source_url == SOURCE_URL
    assert swe.retrieved_at == RETRIEVED_AT


def test_persists_parsed_occupations(db_session):
    result = parse_anzsco_occupations(FIXTURE, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT)
    db_session.add_all(result)
    db_session.commit()

    from koshi.models.occupations import Occupation

    found = db_session.get(Occupation, "254499")
    assert found.name == "Registered Nurse (Aged Care)"
