"""Tests for the SkillSelect invitation-rounds parser.

These run against `skillselect_rounds_live.html`, captured from the live page
on 2026-08-18. The previous tests ran against a synthetic fixture with an
`id="round-results"` table of three columns; no such markup exists on the
real page, which is why the parser passed its tests while extracting zero
rows in production.
"""

import datetime as dt
import html as html_module
import json
import re
from pathlib import Path

import pytest

from koshi.extraction.homeaffairs import HIDDEN_FIELD_ID, HiddenFieldError
from koshi.extraction.skillselect_rounds import parse_skillselect_rounds

FIXTURES = Path(__file__).parent / "fixtures"
LIVE = (FIXTURES / "skillselect_rounds_live.html").read_text(encoding="utf-8")
SOURCE_URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"
RETRIEVED_AT = dt.datetime(2026, 8, 18, tzinfo=dt.timezone.utc)


def _parse(html=LIVE):
    return parse_skillselect_rounds(html, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT)


def _mutate_live_page(mutate) -> str:
    """Rebuild the fixture with each content block passed through `mutate`.

    The payload is JSON-escaped (`\\u003ctd\\u003e`), not HTML-entity-escaped,
    and cells wrap their text in <p>. Editing at the JSON level rather than
    string-replacing escaped markup keeps these tests robust against changes
    in how the page encodes itself.
    """
    raw = re.search(
        rf'id="{re.escape(HIDDEN_FIELD_ID)}"[^>]*\svalue="([^"]*)"', LIVE
    ).group(1)
    payload = json.loads(html_module.unescape(raw))
    for item in payload["content"]:
        item["block"] = mutate(item["block"])
    revalue = html_module.escape(json.dumps(payload), quote=True)
    return LIVE.replace(raw, revalue)


def test_extracts_every_occupation_row_from_the_live_page():
    result = _parse()

    # The live table has exactly 140 occupation rows. The old parser
    # extracted 0 of them.
    assert len(result.rows) == 140
    assert result.skipped == 0


def test_parses_occupation_name_and_threshold():
    rows = {r.occupation_name_raw: r for r in _parse().rows}

    assert rows["Actuary"].threshold_points == 90
    assert rows["Agricultural Consultant"].threshold_points == 80
    assert rows["Carpenter"].threshold_points == 65


def test_occupation_code_is_null_until_the_crosswalk_resolves_it():
    """The source publishes names, never ANZSCO codes. Inventing a code here
    would be fabrication; the crosswalk resolves it in a later step."""
    assert all(r.occupation_code is None for r in _parse().rows)


def test_carries_round_date_and_visa_code_from_the_page():
    rows = _parse().rows

    assert all(r.round_date == dt.date(2026, 6, 4) for r in rows)
    assert all(r.visa_code == "189" for r in rows)


def test_invitations_issued_is_null_at_occupation_grain():
    """Table B has two columns only. Per-round invitation totals exist, but
    at round/subclass grain - attributing 10,000 invitations to each of 140
    occupations would be plainly wrong."""
    assert all(r.invitations_issued is None for r in _parse().rows)


def test_carries_provenance():
    row = _parse().rows[0]

    assert row.source_url == SOURCE_URL
    assert row.retrieved_at == RETRIEVED_AT
    assert row.reliability_tier == "official_scraped"


def test_missing_hidden_field_raises_rather_than_returning_zero_rows():
    with pytest.raises(HiddenFieldError):
        _parse("<html><body><p>redesigned</p></body></html>")


def test_wrong_column_count_fails_loudly_instead_of_skipping_every_row():
    """The regression that motivated this rewrite: the old parser unpacked 3
    cells from this 2-column table, so all 140 rows raised, were caught, and
    were skipped - reporting a clean run with zero rows. A shape mismatch is
    a page-level failure and must be raised once, not swallowed per row."""
    three_col = _mutate_live_page(
        lambda b: b.replace("<p>Actuary</p>\n\t\t\t</td>",
                            "<p>Actuary</p>\n\t\t\t</td><td><p>x</p></td>")
    )
    assert three_col != LIVE, "fixture markup changed - update this test"

    with pytest.raises(HiddenFieldError, match="columns"):
        _parse(three_col)


def test_skips_an_individual_unparseable_row_without_losing_the_rest():
    """Row-level tolerance still applies *within* a correctly shaped table -
    one bad score must not cost the other 139 rows."""
    broken = _mutate_live_page(lambda b: b.replace("<p>90</p>", "<p>n/a</p>", 1))
    assert broken != LIVE, "fixture markup changed - update this test"

    result = parse_skillselect_rounds(
        broken, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT
    )

    assert len(result.rows) == 139
    assert result.skipped == 1
