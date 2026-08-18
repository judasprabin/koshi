"""Parser for the ABS ANZSCO structure workbook.

`anzsco 2022 structure 062023.xlsx` is the classification's own code/title
list. Table 6 is the flat `Code | Title` sheet - 1,425 six-digit pairs - and
is koshi's fallback when LIN 19/051 does not name an occupation.

Read with the standard library (`zipfile` + `ElementTree`) rather than
pandas/openpyxl: an .xlsx is a zip of XML, the sheet is a plain grid, and
koshi does not otherwise need a spreadsheet dependency. The same technique
is what BP0068's pivot cache will require, where openpyxl returns nothing
useful at all.

Caveat: Table 6 is the *coder* list, so it is a superset of the real
occupation set - it includes non-occupation codes such as `099960 Retired`
and `099970 Unemployed`. That is harmless for name->code resolution (those
titles never appear in an invitation round) but means this table should not
be treated as the occupation universe.
"""

import dataclasses
import logging
import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

ANZSCO_EDITION = "2022"
DEFAULT_SHEET = "Table 6"   # flat coder list: name -> code resolution
OCCUPATION_SHEET = "Table 5"  # the classification proper: the real occupation set

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_DIGITS_RE = re.compile(r"\d+")


class AbsWorkbookError(ValueError):
    """The workbook was unreadable or did not have the expected sheet."""


@dataclasses.dataclass
class AbsTitle:
    title: str
    occupation_code: str
    anzsco_edition: str = ANZSCO_EDITION


@dataclasses.dataclass
class ParseResult:
    rows: list[AbsTitle]
    skipped: int


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        si.text if si.text is not None else "".join(t.text or "" for t in si.iter(f"{_NS}t"))
        for si in root.iter(f"{_NS}si")
    ]


def _sheet_path(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = {
        rel.get("Id"): rel.get("Target")
        for rel in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    }
    for sheet in workbook.iter(f"{_NS}sheet"):
        if (sheet.get("name") or "").strip().casefold() == sheet_name.casefold():
            target = (rels.get(sheet.get(f"{_REL_NS}id")) or "").lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    available = [s.get("name") for s in workbook.iter(f"{_NS}sheet")]
    raise AbsWorkbookError(f"sheet {sheet_name!r} not found; workbook has {available!r}")


def _row_values(row, shared: list[str]) -> list[str]:
    values = []
    for cell in row.iter(f"{_NS}c"):
        value = cell.find(f"{_NS}v")
        if value is None:
            values.append("")
        elif cell.get("t") == "s":
            index = int(value.text)
            values.append(shared[index] if index < len(shared) else "")
        else:
            values.append(value.text or "")
    return [v.strip() for v in values]


def parse_abs_occupations(
    workbook_bytes: bytes, *, sheet_name: str = OCCUPATION_SHEET
) -> ParseResult:
    """Parse the hierarchy sheet into the real occupation set.

    Table 5 is the classification proper - major group -> sub-major -> minor
    -> unit group -> occupation - and its 1,076 six-digit codes are the
    actual occupation universe. Table 6, by contrast, is the coder list and
    includes non-occupations (`099960 Retired`), so it is right for
    resolving a name to a code but wrong for defining what an occupation is.

    Rows are *indented by hierarchy level*, so a code's column position
    varies by depth. Each row is scanned for its first six-digit cell and
    the next non-empty cell is taken as the title, rather than assuming a
    fixed column.
    """
    try:
        archive = zipfile.ZipFile(BytesIO(workbook_bytes))
    except zipfile.BadZipFile as exc:
        raise AbsWorkbookError(f"not a readable .xlsx workbook: {exc}") from exc

    with archive:
        shared = _shared_strings(archive)
        sheet = ET.fromstring(archive.read(_sheet_path(archive, sheet_name)))

        rows: list[AbsTitle] = []
        seen: set[str] = set()
        skipped = 0
        for row in sheet.iter(f"{_NS}row"):
            values = _row_values(row, shared)
            code_index = next(
                (i for i, v in enumerate(values) if _DIGITS_RE.fullmatch(v) and len(v) == 6),
                None,
            )
            if code_index is None:
                continue  # heading/spacer/higher-level row, not a data problem
            code = values[code_index]
            title = next((v for v in values[code_index + 1:] if v and not v.isdigit()), "")
            if not title:
                logger.warning("skipping ABS occupation row %r: no title", values)
                skipped += 1
                continue
            if code in seen:
                continue
            seen.add(code)
            rows.append(AbsTitle(title=title, occupation_code=code))

    if not rows:
        raise AbsWorkbookError(
            f"sheet {sheet_name!r} yielded no occupations - possible format change"
        )
    return ParseResult(rows=rows, skipped=skipped)


def parse_abs_titles(workbook_bytes: bytes, *, sheet_name: str = DEFAULT_SHEET) -> ParseResult:
    """Parse the workbook's flat Code | Title sheet into title/code pairs."""
    try:
        archive = zipfile.ZipFile(BytesIO(workbook_bytes))
    except zipfile.BadZipFile as exc:
        raise AbsWorkbookError(f"not a readable .xlsx workbook: {exc}") from exc

    with archive:
        shared = _shared_strings(archive)
        sheet = ET.fromstring(archive.read(_sheet_path(archive, sheet_name)))

        rows: list[AbsTitle] = []
        skipped = 0
        for row in sheet.iter(f"{_NS}row"):
            values = _row_values(row, shared)
            if len(values) < 2:
                continue  # spacer/blank rows, not data problems
            match = _DIGITS_RE.fullmatch(values[0])
            title = values[1]
            if match is None or len(values[0]) != 6 or not title:
                # Header and heading rows land here; only count a skip when
                # the row looked like data but could not be used.
                if values[0] and values[0][0].isdigit():
                    logger.warning("skipping ABS row %r", values[:2])
                    skipped += 1
                continue
            rows.append(AbsTitle(title=title, occupation_code=values[0]))

    if not rows:
        raise AbsWorkbookError(
            f"sheet {sheet_name!r} yielded no code/title pairs - possible format change"
        )
    return ParseResult(rows=rows, skipped=skipped)
