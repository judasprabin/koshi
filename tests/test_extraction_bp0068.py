"""Tests for the BP0068 pivot-cache reader.

The real workbook is 5 MB, too large to ship as a fixture, so these build a
minimal workbook carrying the **verified real structure**: an
`xl/pivotCache/pivotCacheDefinition1.xml` declaring named cache fields with
shared items, and `pivotCacheRecords1.xml` holding `<x v="i"/>` index rows
followed by an `<n v="…"/>` measure.

That structure was confirmed against the live 5 MB file, which parses to
622,425 records across 10 program years, 62 subclasses and 1,710,097
grants in ~4.7s.
"""

import zipfile
from io import BytesIO

import pytest

from koshi.extraction.bp0068 import Bp0068Error, parse_bp0068_grants

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def _workbook(fields, records, *, include_cache=True) -> bytes:
    """Build a minimal .xlsx with a BP0068-shaped pivot cache."""
    definition = f"<pivotCacheDefinition {NS} recordCount=\"{len(records)}\"><cacheFields>"
    for name, items in fields:
        shared = "".join(f'<s v="{v}"/>' for v in items)
        definition += f'<cacheField name="{name}"><sharedItems>{shared}</sharedItems></cacheField>'
    definition += "</cacheFields></pivotCacheDefinition>"

    rows = ""
    for indexes, measure in records:
        rows += "<r>" + "".join(f'<x v="{i}"/>' for i in indexes) + f'<n v="{measure}"/></r>'
    cache_records = f"<pivotCacheRecords {NS}>{rows}</pivotCacheRecords>"

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", f"<workbook {NS}></workbook>")
        if include_cache:
            archive.writestr("xl/pivotCache/pivotCacheDefinition1.xml", definition)
            archive.writestr("xl/pivotCache/pivotCacheRecords1.xml", cache_records)
    return buffer.getvalue()


FIELDS = [
    ("Programme Year", ["2023-24", "2024-25"]),
    ("Visa Category", ["Skilled", "Family"]),
    ("Visa Subclass", ["189 Skilled Independent", "190 Skilled Nominated", "Not Specified"]),
]

FIELDS_WITH_TYPE = FIELDS + [("Visa Type", ["Points-tested", "Employer Sponsored"])]


def test_aggregates_records_to_year_and_subclass():
    workbook = _workbook(
        FIELDS,
        [((0, 0, 0), 1), ((0, 0, 0), 1), ((0, 0, 0), 3), ((1, 0, 1), 2)],
    )

    result = parse_bp0068_grants(workbook)

    by_key = {(r.program_year, r.visa_code): r.granted_count for r in result.rows}
    assert by_key[("2023-24", "189")] == 5  # 1 + 1 + 3
    assert by_key[("2024-25", "190")] == 2
    assert result.record_count == 4


def test_splits_the_code_from_the_subclass_label():
    result = parse_bp0068_grants(_workbook(FIELDS, [((0, 0, 0), 1)]))

    row = result.rows[0]
    assert row.visa_code == "189"
    assert row.visa_name == "Skilled Independent"
    assert row.visa_category == "Skilled"


def test_skips_non_subclass_aggregates():
    """'Not Specified' is a rollup, not a visa."""
    result = parse_bp0068_grants(
        _workbook(FIELDS, [((0, 0, 0), 1), ((0, 0, 2), 9)])
    )

    assert [r.visa_code for r in result.rows] == ["189"]
    assert result.skipped == 1


def test_missing_pivot_cache_fails_loudly():
    """openpyxl would open this workbook and quietly return empty sheets."""
    workbook = _workbook(FIELDS, [((0, 0, 0), 1)], include_cache=False)

    with pytest.raises(Bp0068Error, match="pivot cache"):
        parse_bp0068_grants(workbook)


def test_renamed_field_fails_loudly_rather_than_misindexing():
    """Fields are located by name, not position. A rename must raise rather
    than silently read a neighbouring column as the subclass."""
    renamed = [("Programme Year", ["2023-24"]), ("Visa Category", ["Skilled"]),
               ("Visa Sub Class", ["189 Skilled Independent"])]

    with pytest.raises(Bp0068Error, match="Visa Subclass"):
        parse_bp0068_grants(_workbook(renamed, [((0, 0, 0), 1)]))


def test_rejects_a_non_workbook():
    with pytest.raises(Bp0068Error):
        parse_bp0068_grants(b"not a zip file")


def test_captures_visa_type():
    """Issue #10: FIELD_TYPE ("Visa Type") is declared in the live pivot
    cache's 18 fields but was never actually extracted into GrantRow — this
    is the concrete, verified part of "widen visa_subclasses to BP0068's
    taxonomy" (the field genuinely exists in the source; a full 5-level
    Program/Category/Type/Sub-type breakdown does not — only Category and
    Type are real pivot-cache fields)."""
    # Record index order matches FIELDS_WITH_TYPE's field order:
    # (year, category, subclass, type).
    result = parse_bp0068_grants(
        _workbook(FIELDS_WITH_TYPE, [((0, 0, 0, 1), 1)])
    )

    row = result.rows[0]
    assert row.visa_type == "Employer Sponsored"


def test_missing_visa_type_field_defaults_to_empty():
    """Unlike Category/Subclass/Year, Visa Type is enrichment, not
    load-bearing — every other test in this file uses FIELDS (no Type
    field) and must keep passing unchanged. A cache without it ships
    visa_type="" rather than raising."""
    result = parse_bp0068_grants(_workbook(FIELDS, [((0, 0, 0), 1)]))

    assert result.rows[0].visa_type == ""
