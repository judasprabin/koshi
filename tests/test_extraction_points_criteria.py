"""Tests for the SkillSelect points-test criteria parser.

Fixture captured from the live page on 2026-08-23:
https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189/points-table
— the sibling of the catalogued (wrong, 404) `/points-tested` URL. Same
hidden-field JSON shape as every other Home Affairs page: zero <table> tags
in the raw HTML, content decoded from a single hidden input.
"""

from pathlib import Path

import pytest

from koshi.extraction.homeaffairs import HiddenFieldError
from koshi.extraction.points_criteria import parse_points_criteria

FIXTURES = Path(__file__).parent / "fixtures"
LIVE_PAGE = (FIXTURES / "points_table_live.html").read_text(encoding="utf-8")


def test_raw_page_contains_no_html_table_tag():
    assert "<table" not in LIVE_PAGE


def test_parses_a_single_table_block():
    result = parse_points_criteria(LIVE_PAGE)

    age_rows = [r for r in result.rows if r.criterion_name == "Age"]
    assert len(age_rows) == 4
    by_band = {r.band_description: r.points_value for r in age_rows}
    assert by_band["at least 18 but less than 25 years"] == 25
    assert by_band["at least  33 but less than 40 years"] == 25


def test_multi_table_block_is_split_by_its_sub_heading():
    """"Skilled employment experience" carries two tables (overseas /
    Australian), each preceded by its own <h3> — the only thing that
    disambiguates them, since both share the same parent block text."""
    result = parse_points_criteria(LIVE_PAGE)

    names = {r.criterion_name for r in result.rows}
    overseas = [n for n in names if n.startswith("Skilled employment experience") and "outside Australia" in n]
    australian = [n for n in names if n.startswith("Skilled employment experience") and "in Australia" in n]
    assert len(overseas) == 1
    assert len(australian) == 1

    overseas_rows = [r for r in result.rows if r.criterion_name == overseas[0]]
    australian_rows = [r for r in result.rows if r.criterion_name == australian[0]]
    assert len(overseas_rows) == 4
    assert len(australian_rows) == 5


def test_overview_prose_block_yields_no_rows():
    """The first block ("Overview") is prose only, no table — must not
    raise and must not silently invent a row for it."""
    result = parse_points_criteria(LIVE_PAGE)

    assert not any(r.criterion_name == "Overview" for r in result.rows)


def test_html_markup_inside_a_cell_is_stripped_to_plain_text():
    """"Partner skills" band descriptions contain an inline <a> tag —
    band_description must be plain text, not raw HTML."""
    result = parse_points_criteria(LIVE_PAGE)

    partner_rows = [r for r in result.rows if r.criterion_name == "Partner skills"]
    assert partner_rows
    assert all("<a" not in r.band_description for r in partner_rows)


def test_covers_every_criterion_with_a_table():
    result = parse_points_criteria(LIVE_PAGE)

    base_names = {r.criterion_name.split(" — ")[0] for r in result.rows}
    assert base_names == {
        "Age",
        "English language skills",
        "Skilled employment experience",
        "Educational qualifications",
        "Specialist education qualification",
        "Australian study requirement",
        "Professional Year in Australia",
        "Credentialled community language",
        "Study in regional Australia",
        "Partner skills",
    }


def test_wrong_root_key_fails_loudly():
    with pytest.raises(HiddenFieldError, match="criteria"):
        parse_points_criteria(LIVE_PAGE, root_key="criteria")


def test_missing_hidden_input_fails_loudly():
    with pytest.raises(HiddenFieldError, match="hidden field"):
        parse_points_criteria("<html><body>redesigned</body></html>")
