"""Tests for the migration program planning-levels parser (data model C15).

Fixture captured from the live page 2026-08-23:
https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels
— same hidden-field JSON pattern as every other Home Affairs page.

docs/superpowers/research/2026-08-16-koshi-source-urls.md corrects the
data model doc's stale claim that this needs manual PDF curation: "was
catalogued as tier 5 / PDF — wrong... no PDFs on this page at all."

The table itself is the real complexity here, not the fetch:
- A 3-year pivot (2024-25 / 2025-26 / 2026-27) that must unpivot into one
  row per (program_year, stream_name).
- Row-spanning: a stream's category cell is only populated on its first
  row ("Commonwealth Program" | "Skilled Independent" | ...), continuation
  rows carry an empty first cell ("" | "Talent and Innovation" | ...).
- Footnote markers in <sup> tags glued onto both labels and values with
  no separating space ("Talent and Innovation<sup>1</sup>",
  "3,500<sup>2</sup>") — must be stripped, not parsed as part of the text.
- "Total ..." rows and the genuine "Special Eligibility" leaf are
  IDENTICAL in HTML shape (both colspan=2 on a 4-cell row) — only the
  "Total " text prefix distinguishes a derivable aggregate (skip) from a
  real leaf stream (keep).
"""

from pathlib import Path

import pytest

from koshi.extraction.homeaffairs import HiddenFieldError
from koshi.extraction.program_allocation import parse_program_allocation

FIXTURES = Path(__file__).parent / "fixtures"
LIVE_PAGE = (FIXTURES / "planning_levels_live.html").read_text(encoding="utf-8")


def test_raw_page_contains_no_html_table_tag():
    assert "<table" not in LIVE_PAGE


def test_unpivots_three_years_per_stream():
    result = parse_program_allocation(LIVE_PAGE)

    skilled_independent = [r for r in result.rows if r.stream_name == "Skilled Independent"]
    assert {r.program_year for r in skilled_independent} == {"2024-25", "2025-26", "2026-27"}
    by_year = {r.program_year: r.places for r in skilled_independent}
    assert by_year["2024-25"] == 16900
    assert by_year["2026-27"] == 21090


def test_footnote_markers_are_stripped_from_both_label_and_value():
    result = parse_program_allocation(LIVE_PAGE)

    talent = [r for r in result.rows if r.stream_name == "Talent and Innovation"]
    assert talent, "footnote-suffixed label must still be found stripped"
    by_year = {r.program_year: r.places for r in talent}
    assert by_year["2026-27"] == 3500  # not 35002


def test_continuation_rows_use_the_carried_forward_category_implicitly():
    """"Talent and Innovation" and "State/Territory Nominated" are
    continuation rows (empty first cell in the source) — must still
    produce a row, keyed on the stream cell alone, not silently dropped
    for lacking their own category cell."""
    result = parse_program_allocation(LIVE_PAGE)

    names = {r.stream_name for r in result.rows}
    assert "Talent and Innovation" in names
    assert "State/Territory Nominated" in names


def test_total_rows_are_excluded_as_derivable_aggregates():
    result = parse_program_allocation(LIVE_PAGE)

    names = {r.stream_name for r in result.rows}
    assert not any(n.startswith("Total") for n in names)


def test_special_eligibility_leaf_is_kept_despite_identical_shape_to_a_total_row():
    """Same colspan=2, 4-cell HTML shape as every "Total ..." row — only
    the missing "Total " prefix says this one is real leaf data."""
    result = parse_program_allocation(LIVE_PAGE)

    special = [r for r in result.rows if r.stream_name == "Special Eligibility"]
    assert len(special) == 3  # one per program year
    by_year = {r.program_year: r.places for r in special}
    assert by_year["2024-25"] == 300


def test_section_header_rows_produce_no_rows():
    """"Skilled Migration Program" / "Australian Family Program" are
    colspan=5 section dividers, not data."""
    result = parse_program_allocation(LIVE_PAGE)

    names = {r.stream_name for r in result.rows}
    assert "Skilled Migration Program" not in names
    assert "Australian Family Program" not in names


def test_missing_hidden_input_fails_loudly():
    with pytest.raises(HiddenFieldError, match="hidden field"):
        parse_program_allocation("<html><body>redesigned</body></html>")
