"""Parser for BP0068 — permanent migration program outcomes.

`Permanent Migration Program (Skilled & Family) Outcomes Snapshot` is
published by Home Affairs on data.gov.au under CC-BY 2.5. It is the source
for `application_funnel.granted_count`, which the design had expected to
ship NULL for want of any pathway-level grant breakdown.

**The data is not in the worksheets.** The workbook is a pivot table whose
records live in `xl/pivotCache/pivotCacheRecords1.xml`; the sheets hold
only the rendered view. `pandas`/`openpyxl` therefore return nothing
useful. Records are read here with the standard library.

Encoding: `pivotCacheDefinition1.xml` declares 18 cache fields, each with a
list of shared items; every record is a row of `<x v="i"/>` indexes into
those lists, followed by `<n v="…"/>` — the numeric measure (grants).

Scale: 622,425 records across 10 program years, 62 visa subclasses and 764
occupations. Records are streamed with `iterparse` and aggregated on the
fly rather than materialised, so peak memory stays flat.
"""

import dataclasses
import logging
import re
import zipfile
from collections import defaultdict
from io import BytesIO
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

CACHE_DEFINITION = "xl/pivotCache/pivotCacheDefinition1.xml"
CACHE_RECORDS = "xl/pivotCache/pivotCacheRecords1.xml"

FIELD_PROGRAM_YEAR = "Programme Year"
FIELD_SUBCLASS = "Visa Subclass"
FIELD_CATEGORY = "Visa Category"
FIELD_TYPE = "Visa Type"

# Subclass values are rendered "189 Skilled Independent".
_SUBCLASS_RE = re.compile(r"^\s*(\d{3})\s+(.*)$")


class Bp0068Error(ValueError):
    """The workbook was not the expected BP0068 pivot-cache shape."""


@dataclasses.dataclass
class GrantRow:
    program_year: str
    visa_code: str
    visa_name: str
    visa_category: str
    # Issue #10: FIELD_TYPE is declared in the live pivot cache's 18 fields
    # but was never extracted here — this is the concrete, verified part
    # of "widen visa_subclasses to BP0068's taxonomy" (a full 5-level
    # Program/Category/Type/Sub-type breakdown is not real; Category and
    # Type are the only additional structured fields the source has).
    # Optional (defaults to "" when the field is absent) rather than
    # load-bearing like visa_category/visa_subclass/program_year, since
    # it's enrichment, not identity.
    visa_type: str
    granted_count: int


@dataclasses.dataclass
class ParseResult:
    rows: list[GrantRow]
    record_count: int
    skipped: int


def _cache_fields(archive: zipfile.ZipFile) -> list[tuple[str, list[str]]]:
    try:
        definition = ET.fromstring(archive.read(CACHE_DEFINITION))
    except KeyError as exc:
        raise Bp0068Error(
            f"{CACHE_DEFINITION} not found — this workbook has no pivot cache, "
            f"so it is not BP0068 in the expected shape"
        ) from exc

    fields: list[tuple[str, list[str]]] = []
    for field in definition.iter(f"{_NS}cacheField"):
        shared = field.find(f"{_NS}sharedItems")
        items = [item.get("v") or "" for item in shared] if shared is not None else []
        fields.append((field.get("name") or "", items))
    if not fields:
        raise Bp0068Error("pivot cache declares no fields — format change")
    return fields


def parse_bp0068_grants(workbook_bytes: bytes) -> ParseResult:
    """Aggregate BP0068's records into grants per (program year, subclass).

    The published grain is far finer than koshi needs - it also carries
    citizenship, gender, age, location and occupation - so records are
    summed down to the funnel's grain during the stream.
    """
    try:
        archive = zipfile.ZipFile(BytesIO(workbook_bytes))
    except zipfile.BadZipFile as exc:
        raise Bp0068Error(f"not a readable .xlsx workbook: {exc}") from exc

    with archive:
        fields = _cache_fields(archive)
        names = [name for name, _ in fields]
        try:
            year_index = names.index(FIELD_PROGRAM_YEAR)
            subclass_index = names.index(FIELD_SUBCLASS)
            category_index = names.index(FIELD_CATEGORY)
        except ValueError as exc:
            raise Bp0068Error(
                f"expected fields {FIELD_PROGRAM_YEAR!r}, {FIELD_SUBCLASS!r} and "
                f"{FIELD_CATEGORY!r}; cache carries {names!r}"
            ) from exc
        # Enrichment, not identity: absent in some workbook shapes without
        # invalidating the load, unlike the three fields above.
        type_index = names.index(FIELD_TYPE) if FIELD_TYPE in names else None

        totals: dict[tuple[str, str], int] = defaultdict(int)
        categories: dict[str, str] = {}
        types: dict[str, str] = {}
        record_count = 0
        skipped = 0

        with archive.open(CACHE_RECORDS) as handle:
            for event, element in ET.iterparse(handle, events=("end",)):
                if element.tag != f"{_NS}r":
                    continue
                record_count += 1
                cells = list(element)
                try:
                    year = fields[year_index][1][int(cells[year_index].get("v"))]
                    subclass = fields[subclass_index][1][int(cells[subclass_index].get("v"))]
                    category = fields[category_index][1][int(cells[category_index].get("v"))]
                    visa_type = (
                        fields[type_index][1][int(cells[type_index].get("v"))]
                        if type_index is not None
                        else ""
                    )
                    # The trailing numeric cell is the measure.
                    measure = cells[-1]
                    count = int(float(measure.get("v"))) if measure.tag == f"{_NS}n" else 1
                except (IndexError, TypeError, ValueError):
                    skipped += 1
                else:
                    totals[(year, subclass)] += count
                    categories[subclass] = category
                    types[subclass] = visa_type
                # Free the parsed element: 622k records must not accumulate.
                element.clear()

    if record_count == 0:
        raise Bp0068Error("pivot cache contained no records — format change")

    rows: list[GrantRow] = []
    for (year, subclass), count in sorted(totals.items()):
        match = _SUBCLASS_RE.match(subclass)
        if match is None:
            # Non-subclass aggregates ("Not Specified") are not visa rows.
            skipped += 1
            continue
        rows.append(
            GrantRow(
                program_year=year,
                visa_code=match.group(1),
                visa_name=match.group(2).strip(),
                visa_category=categories.get(subclass, ""),
                visa_type=types.get(subclass, ""),
                granted_count=count,
            )
        )
    logger.info(
        "bp0068: %d records aggregated into %d (year, subclass) rows",
        record_count, len(rows),
    )
    # BP0068 is confidentialised, so perturbation of small cells can push an
    # aggregate below zero. Stored as published rather than clamped, but
    # surfaced: a *rise* in these would indicate a parsing problem, not a
    # privacy artefact.
    negatives = [r for r in rows if r.granted_count < 0]
    if negatives:
        logger.warning(
            "bp0068: %d row(s) have a negative grant count (confidentialisation "
            "artefact, stored as published), e.g. %r",
            len(negatives),
            [(r.visa_code, r.program_year, r.granted_count) for r in negatives[:3]],
        )
    return ParseResult(rows=rows, record_count=record_count, skipped=skipped)
