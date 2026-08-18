"""Tests for the SkillSelect previous-rounds archive parser.

Runs against a fixture captured live on 2026-08-18, reduced to 6 of the 19
archived rounds: the 4 that carry occupation tables (covering both column
shapes) plus 2 summary-only rounds.
"""

import datetime as dt
from pathlib import Path

import pytest

from koshi.extraction.homeaffairs import HiddenFieldError
from koshi.extraction.skillselect_previous_rounds import (
    parse_skillselect_previous_rounds,
)

FIXTURES = Path(__file__).parent / "fixtures"
LIVE = (FIXTURES / "skillselect_previous_rounds_live.html").read_text(encoding="utf-8")
SOURCE_URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/previous-rounds"
RETRIEVED_AT = dt.datetime(2026, 8, 18, tzinfo=dt.timezone.utc)


def _parse(html=LIVE):
    return parse_skillselect_previous_rounds(
        html, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT
    )


def test_parses_every_round_that_carries_occupation_data():
    result = _parse()

    assert result.rounds_parsed == 4
    assert result.rounds_without_occupations == 2  # summary-only, not failures
    assert result.skipped == 0


def test_extracts_history_across_multiple_round_dates():
    dates = {r.round_date for r in _parse().rows}

    assert len(dates) == 4
    assert dt.date(2025, 11, 13) in dates
    assert dt.date(2024, 9, 5) in dates


def test_reads_the_round_date_from_the_item_not_the_stale_heading_id():
    """The heading's id attribute says 13062024 on a round titled
    13 November 2025, so the item title governs."""
    dates = {r.round_date for r in _parse().rows}

    assert dt.date(2024, 6, 13) not in dates


def test_splits_a_multi_subclass_round_into_one_row_per_subclass():
    """Recent rounds publish Occupation | 189 | 491 - a column per visa."""
    rows = [r for r in _parse().rows if r.round_date == dt.date(2025, 11, 13)]

    assert {r.visa_code for r in rows} == {"189", "491"}


def test_skips_not_invited_cells_rather_than_recording_a_zero():
    """'N/A*' means not invited in that subclass, which is not a score."""
    rows = [
        r for r in _parse().rows
        if r.round_date == dt.date(2025, 11, 13) and r.occupation_name_raw == "Actuary"
    ]

    assert [r.visa_code for r in rows] == ["189"]  # 491 was N/A*
    assert rows[0].threshold_points == 85


def test_handles_single_subclass_rounds():
    rows = [r for r in _parse().rows if r.round_date == dt.date(2024, 11, 7)]

    assert rows
    assert {r.visa_code for r in rows} == {"189"}


def test_occupation_code_is_null_pending_the_crosswalk():
    assert all(r.occupation_code is None for r in _parse().rows)


def test_carries_provenance():
    row = _parse().rows[0]

    assert row.source_url == SOURCE_URL
    assert row.reliability_tier == "official_scraped"


def test_missing_hidden_field_raises():
    with pytest.raises(HiddenFieldError):
        _parse("<html><body>redesigned</body></html>")
