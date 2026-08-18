"""Tests for the Home Affairs hidden-field decoder.

Every immi.homeaffairs.gov.au page ships its content as HTML-entity-encoded
JSON inside a hidden input; none of them contain a <table> tag in the raw
HTML. These tests run against a fixture captured from the live page on
2026-08-18, so a page redesign shows up as a test failure rather than as a
silent zero-row extraction in production.
"""

from pathlib import Path

import pytest

from koshi.extraction.homeaffairs import (
    HiddenFieldError,
    decode_hidden_field,
    find_table_after_heading,
)

FIXTURES = Path(__file__).parent / "fixtures"
LIVE_PAGE = (FIXTURES / "skillselect_rounds_live.html").read_text(encoding="utf-8")


def test_raw_page_contains_no_html_table_tag():
    """The finding that root-caused both broken parsers: these pages carry no
    table markup at all, so any parser reaching for <table> in the raw HTML
    finds nothing."""
    assert "<table" not in LIVE_PAGE


def test_decodes_live_page_into_content_blocks():
    blocks = decode_hidden_field(LIVE_PAGE, root_key="content")

    assert len(blocks) == 5
    assert all(isinstance(b, str) for b in blocks)
    # The tables live inside the decoded blocks, not the outer page.
    assert "<table" in blocks[3]


def test_decoded_block_contains_the_expected_headings():
    blocks = decode_hidden_field(LIVE_PAGE, root_key="content")

    assert "Invitations issued by occupation and minimum score invited" in blocks[3]


def test_wrong_root_key_fails_loudly_rather_than_returning_empty():
    """previous-rounds uses `criteria` where this page uses `content`. A
    parser that guesses wrong must raise, not silently extract zero rows —
    the whole point of storing the root key per resource."""
    with pytest.raises(HiddenFieldError, match="criteria"):
        decode_hidden_field(LIVE_PAGE, root_key="criteria")


def test_missing_hidden_input_fails_loudly():
    with pytest.raises(HiddenFieldError, match="hidden field"):
        decode_hidden_field("<html><body>redesigned</body></html>", root_key="content")


def test_find_table_after_heading_locates_the_occupation_table():
    blocks = decode_hidden_field(LIVE_PAGE, root_key="content")

    table = find_table_after_heading(
        blocks[3], heading_contains="by occupation and minimum score"
    )

    rows = table.find("tbody").find_all("tr")
    assert len(rows) == 140
    # Two columns - the shape the old parser got wrong by unpacking three.
    assert len(rows[0].find_all("td")) == 2
    assert [c.get_text(strip=True) for c in rows[0].find_all("td")] == ["Actuary", "90"]


def test_find_table_after_heading_raises_when_heading_absent():
    with pytest.raises(HiddenFieldError, match="no heading"):
        find_table_after_heading("<h3>Something else</h3><table></table>",
                                 heading_contains="by occupation and minimum score")
