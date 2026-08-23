"""Tests for the SkillSelect page's Tables A/C/D — round totals, the
monthly invitation matrix, and state/territory nominations.

Issue #25: these three tables are decoded by the same hidden-field JSON
that Table B (occupation minimum scores) already uses, but were never
parsed — a "free win" that turned out to need three new tables, since none
of the 22-table catalog has a matching shape for round-level or
program-year aggregates.

Reuses the existing `skillselect_rounds_live.html` fixture (2025-26
program year) for the happy path; a small synthetic fixture below covers
Table D's privacy-suppressed cells ("<5"), which this program-year
snapshot doesn't happen to contain.
"""

from pathlib import Path

import pytest

from koshi.extraction.homeaffairs import HiddenFieldError
from koshi.extraction.skillselect_summary import parse_skillselect_summary

FIXTURES = Path(__file__).parent / "fixtures"
LIVE_PAGE = (FIXTURES / "skillselect_rounds_live.html").read_text(encoding="utf-8")


def test_parses_round_totals():
    result = parse_skillselect_summary(LIVE_PAGE)

    assert len(result.round_totals) == 1
    row = result.round_totals[0]
    assert row.visa_code == "189"
    assert row.visa_label == "Skilled Independent visa (subclass 189)"
    assert row.round_date.isoformat() == "2026-06-04"
    assert row.total_invited == 10000
    assert row.tie_break_date == "24/04/2026"


def test_parses_monthly_invitations_for_every_subclass_and_month():
    result = parse_skillselect_summary(LIVE_PAGE)

    # 2 subclass rows x 12 months.
    assert len(result.monthly_invitations) == 24
    by_key = {
        (r.visa_code, r.visa_label, r.month): r.invited_count
        for r in result.monthly_invitations
    }
    assert by_key[("189", "Skilled Independent visa (subclass 189)", "Aug")] == 6887
    assert by_key[("189", "Skilled Independent visa (subclass 189)", "Jul")] == 0
    assert all(r.program_year == "2025-26" for r in result.monthly_invitations)


def test_parses_state_nominations_with_the_reporting_period():
    result = parse_skillselect_summary(LIVE_PAGE)

    # 2 subclass rows x 8 states/territories.
    assert len(result.state_nominations) == 16
    row = next(
        r for r in result.state_nominations
        if r.visa_label == "Skilled Nominated visa (subclass 190)" and r.state_code == "NSW"
    )
    assert row.visa_code == "190"
    assert row.nominated_count == 2100
    assert row.suppressed is False
    assert row.period_start.isoformat() == "2025-07-01"
    assert row.period_end.isoformat() == "2026-06-30"


def test_different_streams_of_the_same_subclass_are_not_collapsed():
    """Table C's 491 row is "Family Sponsored"; Table D's 491 row is
    "State and Territory Nominated" — same 3-digit code, different real
    visas. visa_label must be what actually distinguishes them, since
    visa_code alone would silently merge two different things."""
    result = parse_skillselect_summary(LIVE_PAGE)

    monthly_491_labels = {r.visa_label for r in result.monthly_invitations if r.visa_code == "491"}
    state_491_labels = {r.visa_label for r in result.state_nominations if r.visa_code == "491"}
    assert monthly_491_labels == {"Skilled Work Regional (Provisional) visa (subclass 491) – Family Sponsored"}
    assert state_491_labels == {"Skilled Work Regional (Provisional) visa (subclass 491) State and Territory Nominated"}
    assert monthly_491_labels != state_491_labels


SUPPRESSED_BLOCK4 = """
<h3>2026-27 program year</h3>
<p>The number of EOIs that have received nominations from state and
territory governments from 1 July 2026 to 31 July 2026.</p>
<table>
<thead><tr><th>Visa subclass</th><th>ACT</th><th>NSW</th></tr></thead>
<tbody>
<tr><td>Skilled Nominated visa (subclass 190)</td><td>&lt;5</td><td>146</td></tr>
</tbody>
</table>
"""


def _payload_with_state_block(block4_html: str) -> str:
    import html as html_module
    import json

    payload = {
        "content": [
            {"id": -1, "text": "Overview", "block": "<p>overview</p>"},
            {"text": "State and Territory nominations", "block": block4_html},
        ]
    }
    escaped = html_module.escape(json.dumps(payload), quote=True)
    return (
        f'<html><body><input type="hidden" '
        f'id="ctl00_PlaceHolderMain_PageSchemaHiddenField_Input" '
        f'value="{escaped}"></body></html>'
    )


def test_suppressed_cells_are_not_fabricated_as_a_number():
    """"<5" is a real published value (privacy suppression), not a
    parse failure — must not be skipped, and must not be guessed at as a
    specific integer, same philosophy as BP0068's negative-count handling."""
    page = _payload_with_state_block(SUPPRESSED_BLOCK4)

    result = parse_skillselect_summary(page)

    act_row = next(r for r in result.state_nominations if r.state_code == "ACT")
    nsw_row = next(r for r in result.state_nominations if r.state_code == "NSW")
    assert act_row.suppressed is True
    assert act_row.nominated_count is None
    assert nsw_row.suppressed is False
    assert nsw_row.nominated_count == 146
    # This fixture has no "Current round" block at all — that section must
    # degrade to empty, not crash the whole page.
    assert result.round_totals == []
    assert result.monthly_invitations == []


def test_missing_hidden_input_fails_loudly():
    with pytest.raises(HiddenFieldError, match="hidden field"):
        parse_skillselect_summary("<html><body>redesigned</body></html>")
