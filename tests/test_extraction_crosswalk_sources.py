"""Tests for the two occupation name->code sources.

Both run against fixtures captured live on 2026-08-18:
  - LIN 19/051 (legislation.gov.au epub) Table 5 - the binding instrument
  - ABS ANZSCO 2022 structure workbook Table 6 - the classification list

Neither source alone resolves every occupation SkillSelect publishes, which
is why koshi carries both. See test_occupation_crosswalk.py for the
resolution rule.
"""

from pathlib import Path

import pytest

from koshi.extraction.abs_anzsco import AbsWorkbookError, parse_abs_titles
from koshi.extraction.lin19051 import (
    Lin19051Error,
    LIN_LIST_TABLES,
    parse_lin_occupation_lists,
    parse_lin_titles,
)

FIXTURES = Path(__file__).parent / "fixtures"
LIN = (FIXTURES / "lin19051_tables_live.html").read_text(encoding="utf-8")
ABS_XLSX = (FIXTURES / "abs_anzsco_2022_structure.xlsx").read_bytes()


# --- LIN 19/051 -------------------------------------------------------

def test_lin_table_5_yields_the_full_occupation_authority_list():
    result = parse_lin_titles(LIN)

    assert len(result.rows) == 504
    assert result.skipped == 0


def test_lin_rows_carry_name_code_and_assessing_authority():
    by_code = {r.occupation_code: r for r in parse_lin_titles(LIN).rows}

    row = by_code["133111"]
    assert row.title == "construction project manager"
    assert row.assessing_authority  # column 3 is populated


def test_lin_codes_are_all_six_digit():
    assert all(len(r.occupation_code) == 6 for r in parse_lin_titles(LIN).rows)


def test_lin_positional_table_shift_fails_loudly():
    """The epub's 12 tables carry no id or class, so they can only be
    addressed positionally - which silently returns different data if the
    document gains a table. The row-count assertion is the guard."""
    shifted = LIN.replace("<body>", "<body><table><tr><td>decoy</td></tr></table>", 1)

    with pytest.raises(Lin19051Error, match="row"):
        parse_lin_titles(shifted)


def test_lin_occupation_lists_carry_the_three_skilled_lists():
    """Tables 1-3 are MLTSSL / STSOL / ROL membership."""
    lists = parse_lin_occupation_lists(LIN)

    assert {entry[0] for entry in LIN_LIST_TABLES} == {"MLTSSL", "STSOL", "ROL"}
    assert len(lists["MLTSSL"]) == 212
    assert len(lists["STSOL"]) == 215
    assert len(lists["ROL"]) == 77


# --- ABS ANZSCO workbook ----------------------------------------------

def test_abs_table_6_yields_every_code_title_pair():
    result = parse_abs_titles(ABS_XLSX)

    assert len(result.rows) == 1425
    assert result.skipped == 0


def test_abs_rows_carry_title_and_code():
    by_code = {r.occupation_code: r for r in parse_abs_titles(ABS_XLSX).rows}

    assert by_code["111111"].title == "Chief Executive or Managing Director"
    assert by_code["221111"].title == "Accountant (General)"


def test_abs_missing_sheet_fails_loudly():
    with pytest.raises(AbsWorkbookError, match="Table 6"):
        parse_abs_titles(ABS_XLSX, sheet_name="Table 99")


def test_abs_rejects_a_non_workbook():
    with pytest.raises(AbsWorkbookError):
        parse_abs_titles(b"not a zip file at all")
