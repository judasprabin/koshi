"""Tests for the ANZSCO occupations parser.

These run against `anzsco_occupations_live.html`, captured from the live page
on 2026-08-18. The previous tests used a synthetic `<table id="occupation-list">`
fixture; the page is a Drupal Views card grid and contains no table markup at
all, which is why the parser passed its tests while extracting nothing.
"""

import datetime as dt
from pathlib import Path

import pytest

from koshi.extraction.anzsco_occupations import (
    AnzscoPageError,
    has_next_page,
    parse_anzsco_occupations,
)

FIXTURES = Path(__file__).parent / "fixtures"
LIVE = (FIXTURES / "anzsco_occupations_live.html").read_text(encoding="utf-8")
SOURCE_URL = "https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco"
RETRIEVED_AT = dt.datetime(2026, 8, 18, tzinfo=dt.timezone.utc)


def _parse(html=LIVE):
    return parse_anzsco_occupations(html, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT)


def test_raw_page_contains_no_table_markup():
    """The finding that root-caused this parser's failure."""
    assert "<table" not in LIVE
    assert 'id="occupation-list"' not in LIVE


def test_extracts_every_card_on_the_page():
    result = _parse()

    assert len(result.rows) == 12  # the live page paginates at 12 per page
    assert result.skipped == 0


def test_parses_code_and_name_from_a_card():
    by_code = {r.code: r for r in _parse().rows}

    assert by_code["422111"].name == (
        "Aboriginal and Torres Strait Islander Education Workers"
    )
    assert by_code["221111"].name == "Accountants (General)"


def test_strips_the_anzsco_prefix_from_the_code():
    """Cards render the code as 'ANZSCO 422111'; the PK is the bare code."""
    assert all(r.code.isdigit() for r in _parse().rows)


def test_records_code_grain_because_the_page_mixes_widths():
    """The live listing interleaves 4-digit unit groups (2211 Accountants)
    with 6-digit occupations (221111 Accountants (General)). Without an
    explicit grain marker the two are indistinguishable in the table, and
    joins against sources that use one width or the other go silently
    wrong."""
    by_code = {r.code: r for r in _parse().rows}

    assert by_code["2211"].code_grain == "unit_group"
    assert by_code["221111"].code_grain == "occupation"


def test_derives_unit_group_for_both_widths():
    by_code = {r.code: r for r in _parse().rows}

    assert by_code["221111"].unit_group == "2211"  # 6-digit -> leading 4
    assert by_code["2211"].unit_group == "2211"  # already a unit group


def test_carries_provenance():
    row = _parse().rows[0]

    assert row.source_url == SOURCE_URL
    assert row.retrieved_at == RETRIEVED_AT
    assert row.reliability_tier == "official_scraped"


def test_missing_card_container_fails_loudly_rather_than_returning_zero_rows():
    with pytest.raises(AnzscoPageError, match="no occupation cards"):
        _parse("<html><body><p>redesigned</p></body></html>")


def test_skips_a_single_malformed_card_without_losing_the_rest():
    broken = LIVE.replace(
        '<div class="card_anzsco">ANZSCO 422111</div>', "<div class=\"card_anzsco\"></div>", 1
    )
    assert broken != LIVE, "fixture markup changed - update this test"

    result = parse_anzsco_occupations(
        broken, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT
    )

    assert len(result.rows) == 11
    assert result.skipped == 1


def test_has_next_page_detects_the_pager():
    """The listing is 103 pages of 12; without paging, koshi loads 12 of
    1,236 occupations."""
    assert has_next_page(LIVE, current_page=0) is True
    assert has_next_page(LIVE, current_page=102) is False
