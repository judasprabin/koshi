"""Tests for the English test bands parser (data model C7).

The catalogued Home Affairs English page has zero tables (prose only) —
the real data lives in two legislative instruments, fetched live
2026-08-23:

  - lin25016_schedule2_live.html — LIN 25/016 (F2025L00905) Schedule 2:
    4 bands (Vocational/Competent/Proficient/Superior) x 9 tests x 4
    skills. The real parser hazard: 12 rowspan attributes carry the band
    name and some "Excluded." cells down across all 4 skill sub-rows —
    naive positional td-indexing misaligns everything below the first
    skill row in each band.
  - functional_english_live.html — F2025L00904: Functional English,
    8 tests, one score-type column each (no rowspans, no per-skill
    breakdown — a single overall threshold per test).

Schema note: C7's grain is (test_name, band_level) — one row per test
per band, not per skill. Schedule 2 publishes 4 different skill scores
per (test, band) (they're often NOT equal — e.g. Vocational/PTE reads
listening=33, reading=36, writing=29, speaking=24), so
`score_requirement` carries all four, not one number standing in for all.

points_awarded isn't published in either instrument — these are pure
score-threshold definitions. Mapped from the already-built
points_criteria_reference table's "English language skills" band values
(Competent=0, Proficient=10, Superior=20); Vocational and Functional earn
no points at all under the points test.
"""

from pathlib import Path

from koshi.extraction.english_test_bands import (
    parse_functional_english_bands,
    parse_schedule2_bands,
)

FIXTURES = Path(__file__).parent / "fixtures"
SCHEDULE2 = (FIXTURES / "lin25016_schedule2_live.html").read_text(encoding="utf-8")
FUNCTIONAL = (FIXTURES / "functional_english_live.html").read_text(encoding="utf-8")


def test_schedule2_covers_all_four_bands():
    result = parse_schedule2_bands(SCHEDULE2)

    assert {r.band_level for r in result.rows} == {
        "Vocational", "Competent", "Proficient", "Superior",
    }


def test_schedule2_combines_all_four_skills_into_one_row_per_test_band():
    result = parse_schedule2_bands(SCHEDULE2)

    row = next(r for r in result.rows if r.band_level == "Vocational" and r.test_name == "PTE Academic")
    # Real values from the live document — genuinely different per skill,
    # proving the four scores aren't collapsed into one number.
    assert "Listening 33" in row.score_requirement
    assert "Reading 36" in row.score_requirement
    assert "Writing 29" in row.score_requirement
    assert "Speaking 24" in row.score_requirement


def test_rowspan_carried_band_name_does_not_leak_into_the_wrong_band():
    """The real regression this parser exists to prevent: naive
    td-indexing on Schedule 2's rowspans misattributes scores to the
    wrong band. Superior's PTE listening score (69) must not appear
    under Vocational, and vice versa (33)."""
    result = parse_schedule2_bands(SCHEDULE2)

    vocational_pte = next(r for r in result.rows if r.band_level == "Vocational" and r.test_name == "PTE Academic")
    superior_pte = next(r for r in result.rows if r.band_level == "Superior" and r.test_name == "PTE Academic")
    assert "33" in vocational_pte.score_requirement
    assert "69" in superior_pte.score_requirement
    assert vocational_pte.score_requirement != superior_pte.score_requirement


def test_excluded_test_band_combination_is_skipped_not_stored_as_a_row():
    """C1 Advanced is "Excluded." at Vocational (rowspan=4, spans all
    four skills at once — no per-skill breakdown for an excluded test).
    Excluded means this test doesn't qualify at this band at all, not a
    real score threshold to store."""
    result = parse_schedule2_bands(SCHEDULE2)

    assert not any(
        r.band_level == "Vocational" and r.test_name == "C1 Advanced" for r in result.rows
    )


def test_schedule2_points_awarded_matches_points_criteria_reference():
    result = parse_schedule2_bands(SCHEDULE2)

    by_band = {r.band_level: r.points_awarded for r in result.rows}
    assert by_band["Vocational"] == 0
    assert by_band["Competent"] == 0
    assert by_band["Proficient"] == 10
    assert by_band["Superior"] == 20


def test_schedule2_row_count_matches_36_minus_excluded_combinations():
    """4 bands x 9 tests = 36 combinations; some are "Excluded." per
    the live document and must not appear as rows."""
    result = parse_schedule2_bands(SCHEDULE2)

    assert len(result.rows) < 36
    assert len(result.rows) > 30  # sanity: most combinations are real


def test_functional_english_covers_eight_tests_with_no_skill_breakdown():
    result = parse_functional_english_bands(FUNCTIONAL)

    assert len(result.rows) == 8
    assert all(r.band_level == "Functional" for r in result.rows)
    assert all(r.points_awarded == 0 for r in result.rows)


def test_functional_english_picks_whichever_score_column_is_populated():
    """Each test uses exactly one of three score types (average/overall/
    total band score) — the parser must find the populated one, not
    assume a fixed column."""
    result = parse_functional_english_bands(FUNCTIONAL)

    by_test = {r.test_name: r.score_requirement for r in result.rows}
    assert "4.5" in by_test["IELTS Academic"]  # average band score column
    assert "5" in by_test["CELPIP General"]  # overall band score column
    assert "26" in by_test["TOEFL iBT"]  # total band score column


def test_functional_and_schedule2_test_names_do_not_collide_on_band():
    """Functional is a distinct band from Schedule 2's four — the
    combined (test_name, band_level) unique key never sees "Functional"
    from Schedule 2 or "Vocational" etc. from the Functional instrument."""
    schedule2 = parse_schedule2_bands(SCHEDULE2)
    functional = parse_functional_english_bands(FUNCTIONAL)

    schedule2_bands = {r.band_level for r in schedule2.rows}
    functional_bands = {r.band_level for r in functional.rows}
    assert schedule2_bands.isdisjoint(functional_bands)
