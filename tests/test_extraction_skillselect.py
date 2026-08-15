import datetime as dt
from pathlib import Path

from koshi.extraction.skillselect_rounds import parse_skillselect_rounds

FIXTURE = (Path(__file__).parent / "fixtures" / "skillselect_rounds_sample.html").read_text()
MALFORMED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "skillselect_rounds_sample_malformed.html"
).read_text()
SOURCE_URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"
RETRIEVED_AT = dt.datetime(2026, 7, 25, tzinfo=dt.timezone.utc)


def test_parses_round_date_and_two_rows():
    result = parse_skillselect_rounds(
        FIXTURE, visa_code="189", source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT
    )

    assert len(result.rows) == 2
    assert result.skipped == 0
    swe = next(r for r in result.rows if r.occupation_code == "261313")
    assert swe.round_date == dt.date(2026, 7, 24)
    assert swe.threshold_points == 85
    assert swe.invitations_issued == 120
    assert swe.visa_code == "189"
    assert swe.reliability_tier == "official_scraped"


def test_raises_if_round_date_missing():
    import pytest

    bad_html = "<table id='round-results'><tbody></tbody></table>"
    with pytest.raises(ValueError, match="round date"):
        parse_skillselect_rounds(
            bad_html, visa_code="189", source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT
        )


def test_parses_thousands_separator_and_na_placeholder_skips_malformed_row():
    result = parse_skillselect_rounds(
        MALFORMED_FIXTURE, visa_code="189", source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT
    )
    assert len(result.rows) == 2
    assert result.skipped == 1

    swe = next(r for r in result.rows if r.occupation_code == "261313")
    assert swe.invitations_issued == 1234

    nurse = next(r for r in result.rows if r.occupation_code == "254499")
    assert nurse.invitations_issued is None
