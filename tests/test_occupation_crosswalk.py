"""Tests for the occupation name -> ANZSCO code crosswalk.

The resolution rule is LIN-first, and it is load-bearing rather than a
preference: three titles that appear in a live invitation round resolve to
*different* codes in the two sources, and an ABS-first implementation
returns wrong codes for them without raising anything.
"""

import datetime as dt

import pytest

from koshi.crosswalk import normalize_title, resolve_occupation_code
from koshi.models.occupation_titles import OccupationTitle

RETRIEVED_AT = dt.datetime(2026, 8, 18, tzinfo=dt.timezone.utc)


def _title(session, title, code, source, edition="2013"):
    session.add(
        OccupationTitle(
            title=title,
            title_normalized=normalize_title(title),
            occupation_code=code,
            title_source=source,
            anzsco_edition=edition,
            source_url="https://www.legislation.gov.au/F2019L00278",
            retrieved_at=RETRIEVED_AT,
            reliability_tier="official_scraped",
        )
    )


def test_normalize_folds_case_and_whitespace():
    """LIN renders titles lower case ('construction project manager'),
    SkillSelect title case ('Construction Project Manager')."""
    assert normalize_title("Construction Project Manager") == normalize_title(
        "construction project manager"
    )
    assert normalize_title("  Plumber   (General) ") == normalize_title("Plumber (General)")


def test_resolves_from_lin_when_only_lin_has_the_title(db_session):
    _title(db_session, "Speech Pathologist", "252712", "LIN_19_051")
    db_session.commit()

    assert resolve_occupation_code(db_session, "Speech Pathologist") == "252712"


def test_resolves_from_abs_when_lin_lacks_the_title(db_session):
    _title(db_session, "Chief Executive or Managing Director", "111111", "ABS_ANZSCO", "2022")
    db_session.commit()

    assert resolve_occupation_code(db_session, "Chief Executive or Managing Director") == "111111"


@pytest.mark.parametrize(
    "title, lin_code, abs_code",
    [
        ("Management Consultant", "224711", "224713"),
        ("Plumber (General)", "334111", "334116"),
        ("Statistician", "224113", "224116"),
    ],
)
def test_lin_wins_where_the_two_sources_disagree(db_session, title, lin_code, abs_code):
    """These three really do differ between the sources on the live data.
    LIN 19/051 is the binding instrument, so it governs."""
    _title(db_session, title, lin_code, "LIN_19_051")
    _title(db_session, title, abs_code, "ABS_ANZSCO", "2022")
    db_session.commit()

    assert resolve_occupation_code(db_session, title) == lin_code


def test_returns_none_for_an_unknown_title(db_session):
    assert resolve_occupation_code(db_session, "Wizard (Senior)") is None


def test_matches_case_insensitively(db_session):
    _title(db_session, "construction project manager", "133111", "LIN_19_051")
    db_session.commit()

    assert resolve_occupation_code(db_session, "Construction Project Manager") == "133111"


# --- end-to-end against all three real sources ------------------------

def test_crosswalk_resolves_every_occupation_in_a_live_invitation_round(db_session):
    """The measurement that justifies carrying two sources.

    Runs the real LIN 19/051 epub, the real ABS workbook and the real
    SkillSelect page through the actual parsers and resolver. Neither
    source alone reaches 140/140.
    """
    from pathlib import Path

    from koshi.extraction.abs_anzsco import parse_abs_titles
    from koshi.extraction.lin19051 import parse_lin_titles
    from koshi.extraction.skillselect_rounds import parse_skillselect_rounds

    fixtures = Path(__file__).parent / "fixtures"
    for row in parse_lin_titles(
        (fixtures / "lin19051_tables_live.html").read_text(encoding="utf-8")
    ).rows:
        _title(db_session, row.title, row.occupation_code, "LIN_19_051")
    for row in parse_abs_titles(
        (fixtures / "abs_anzsco_2022_structure.xlsx").read_bytes()
    ).rows:
        _title(db_session, row.title, row.occupation_code, "ABS_ANZSCO", "2022")
    db_session.commit()

    rounds = parse_skillselect_rounds(
        (fixtures / "skillselect_rounds_live.html").read_text(encoding="utf-8"),
        source_url="https://immi.homeaffairs.gov.au/x",
        retrieved_at=RETRIEVED_AT,
    ).rows

    resolved = {
        r.occupation_name_raw: resolve_occupation_code(db_session, r.occupation_name_raw)
        for r in rounds
    }

    assert len(resolved) == 140
    unresolved = [name for name, code in resolved.items() if code is None]
    assert unresolved == []

    # The eight names only LIN carries - an ABS-only build would drop these.
    assert resolved["Speech Pathologist"] is not None
    assert resolved["Cabinetmaker"] is not None
    # And the three where LIN must win.
    assert resolved["Management Consultant"] == "224711"
    assert resolved["Plumber (General)"] == "334111"
    assert resolved["Statistician"] == "224113"
