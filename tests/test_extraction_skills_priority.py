"""Tests for the Jobs and Skills Australia Occupation Shortage List parser
(data model C18).

Two-step source, unlike koshi's other pages: the occupation-shortage-list
page doesn't embed the rating data directly (despite source-urls.md §10
describing it as "splData/splSearch JSON embedded in the page" — that's
stale; the audit predates a site redesign). The actual data lives in a
separate static JSON file whose path is only discoverable from the page's
own Drupal settings config, and the filename changes whenever JSA
republishes (it's literally timestamped: "25-10-10 - splData (1).json").

Fixtures captured live 2026-08-23:
  - skills_priority_list_live.html — the page (41KB, kept whole).
  - skills_priority_data_sample.json — a trimmed real excerpt of the 1.4MB
    splData.json (same exact structure/values, just fewer occupations),
    including one occupation (121312, Beef Cattle Farmer) with genuinely
    different ratings across jurisdictions (NT=S, everywhere else=NS) —
    exactly the "M/R split is itself geographic" case the 2026-08-17
    audit flagged as a real schema-collision risk if jurisdiction isn't
    tracked as its own column.

The real payload nests four dimensions the original C18 spec didn't
account for: code_grain (4-digit unit group vs 6-digit occupation),
edition (2022 = ANZSCO, 2024 = OSCA), year (2021-2025, a real time
series), and jurisdiction (national + 8 states/territories, each with its
own rating). This build scopes to 6-digit/2022 (matches koshi's primary
occupation grain) and the latest year only — 4-digit and the 2024/OSCA
edition are deliberately deferred to the same ANZSCO->OSCA migration
trigger already tracked as issue #13.
"""

import json
from pathlib import Path

import pytest

from koshi.extraction.skills_priority import (
    SkillsPriorityError,
    discover_spl_data_path,
    parse_skills_priority_ratings,
)

FIXTURES = Path(__file__).parent / "fixtures"
LIVE_PAGE = (FIXTURES / "skills_priority_list_live.html").read_text(encoding="utf-8")
SAMPLE_DATA = (FIXTURES / "skills_priority_data_sample.json").read_text(encoding="utf-8")


def test_discovers_the_data_file_path_from_the_page_config():
    path = discover_spl_data_path(LIVE_PAGE)

    assert path.startswith("/system/files/applet_data/")
    assert "splData" in path


def test_missing_config_fails_loudly():
    with pytest.raises(SkillsPriorityError, match="drupal-settings-json"):
        discover_spl_data_path("<html><body>redesigned</body></html>")


def test_parses_one_row_per_jurisdiction_for_the_latest_year():
    result = parse_skills_priority_ratings(SAMPLE_DATA, code_grain="6", edition="2022")

    # 3 occupations in the 6/2022 sample x 9 jurisdictions each.
    assert len(result.rows) == 3 * 9


def test_uses_the_latest_year_present_not_an_arbitrary_one():
    result = parse_skills_priority_ratings(SAMPLE_DATA, code_grain="6", edition="2022")

    rows = [r for r in result.rows if r.occupation_code == "111111"]
    assert {r.jurisdiction for r in rows} == {
        "NAT", "NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT",
    }


def test_different_jurisdictions_can_carry_different_ratings():
    """121312 (Beef Cattle Farmer): NT=S, everywhere else=NS — the exact
    "M/R split is itself geographic" case the audit flagged. A schema
    keyed on occupation_code alone (no jurisdiction column) would collide
    these into one row and silently lose the NT-specific shortage."""
    result = parse_skills_priority_ratings(SAMPLE_DATA, code_grain="6", edition="2022")

    farmer_rows = {r.jurisdiction: r.shortage_rating for r in result.rows if r.occupation_code == "121312"}
    assert farmer_rows["NT"] == "S"
    assert farmer_rows["NSW"] == "NS"
    assert farmer_rows["NAT"] == "NS"


def test_future_demand_rating_is_always_none():
    """Audit finding: JSA's `d` field is null throughout — NO SOURCE."""
    result = parse_skills_priority_ratings(SAMPLE_DATA, code_grain="6", edition="2022")

    assert all(r.future_demand_rating is None for r in result.rows)


def test_grain_and_edition_filter_correctly():
    """The sample carries 6/2022 (3 occupations), 6/2024 (1), and 4/2022
    (1) — requesting one combination must not leak rows from another."""
    six_2024 = parse_skills_priority_ratings(SAMPLE_DATA, code_grain="6", edition="2024")
    four_2022 = parse_skills_priority_ratings(SAMPLE_DATA, code_grain="4", edition="2022")

    assert {r.occupation_code for r in six_2024.rows} == {"111131"}
    assert {r.occupation_code for r in four_2022.rows} == {"1111"}


def test_rating_case_is_normalized():
    """Audit finding: "Ns" appearing in the payload is a casing bug, not
    a fifth value — must be normalized to uppercase before the CHECK
    constraint sees it, defensively, even though this fixture's own
    values are already clean uppercase."""
    lowercased = json.loads(SAMPLE_DATA)
    lowercased["6"]["2022"]["111111"]["v"]["2025"]["rnat"] = "Ns"
    payload = json.dumps(lowercased)

    result = parse_skills_priority_ratings(payload, code_grain="6", edition="2022")

    row = next(r for r in result.rows if r.occupation_code == "111111" and r.jurisdiction == "NAT")
    assert row.shortage_rating == "NS"


def test_unknown_grain_yields_zero_rows_not_an_error():
    """A grain/edition combination absent from the payload (e.g. 4/2024,
    which is genuinely empty in the real source) is a normal "nothing to
    load," not a page-redesign failure."""
    result = parse_skills_priority_ratings(SAMPLE_DATA, code_grain="4", edition="2024")

    assert result.rows == []
