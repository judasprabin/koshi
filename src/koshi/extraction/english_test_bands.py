"""Parser for English language test score bands (data model C7).

The catalogued Home Affairs English page has zero tables (prose only,
confirmed by the 2026-08-17 audit) — the real data lives in two
legislative instruments:

- **LIN 25/016 (F2025L00905) Schedule 2** — 4 bands (Vocational,
  Competent, Proficient, Superior) x 9 tests x 4 skills. Uses 12
  `rowspan` attributes to carry the band name and, for tests not
  accepted at a given band ("Excluded."), the exclusion itself, down
  across all four skill sub-rows. Naive positional `<td>` indexing
  misattributes every skill row below the first one in each band — this
  parser reconstructs the full virtual grid (expanding every rowspan
  explicitly) before reading any row, rather than tracking column
  offsets by hand.
- **F2025L00904** — Functional English, 8 tests, no rowspans and no
  per-skill breakdown: each test uses exactly one of three score types
  (average/overall/total band score).

C7's grain is (test_name, band_level) — one row per test per band, not
per skill. Schedule 2 publishes four independently-varying skill scores
per (test, band) (e.g. Vocational/PTE Academic: listening 33, reading
36, writing 29, speaking 24 — genuinely different numbers), so
`score_requirement` records all four rather than picking one.

`points_awarded` isn't published in either instrument — both are pure
score-threshold definitions. Mapped from the already-built
`points_criteria_reference` table's "English language skills" band
values (Competent=0, Proficient=10, Superior=20); Vocational and
Functional earn no points under the points test.
"""

import dataclasses
import logging
import re
import warnings

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger(__name__)

# Matches koshi's points_criteria_reference build (issue #16): Competent/
# Proficient/Superior English score 0/10/20 there. Vocational and
# Functional aren't in that table at all — they earn no points.
POINTS_BY_BAND = {
    "Functional": 0,
    "Vocational": 0,
    "Competent": 0,
    "Proficient": 10,
    "Superior": 20,
}

_SKILL_SCORE_RE = re.compile(r"^(.+?)\s*\((\w+)\)$")
_SKILL_ORDER = ("listening", "reading", "writing", "speaking")


@dataclasses.dataclass
class EnglishTestBandRow:
    test_name: str
    band_level: str
    score_requirement: str
    points_awarded: int


@dataclasses.dataclass
class ParseResult:
    rows: list[EnglishTestBandRow]
    skipped: int


def _flatten_rowspan_grid(rows: list[Tag]) -> list[list[str]]:
    """Reconstruct the full virtual grid for a table with rowspans.

    A rowspan cell's value is carried down into every row it covers, so
    a continuation row's own <tr> physically omits that cell entirely —
    this walks left to right, filling each column from a still-active
    span before consuming the row's next real <td>, exactly how a
    browser renders it.
    """
    grid: list[list[str]] = []
    pending: dict[int, list[int | str]] = {}  # col -> [remaining_rows, value]

    for tr in rows:
        cells = iter(tr.find_all(["td", "th"]))
        row_out: list[str] = []
        col = 0
        current = next(cells, None)
        while current is not None or col in pending:
            if col in pending:
                remaining, value = pending[col]
                row_out.append(value)
                if remaining - 1 > 0:
                    pending[col] = [remaining - 1, value]
                else:
                    del pending[col]
                col += 1
                continue

            text = current.get_text(strip=True)
            rowspan = int(current.get("rowspan", 1))
            colspan = int(current.get("colspan", 1))
            for _ in range(colspan):
                row_out.append(text)
                if rowspan > 1:
                    pending[col] = [rowspan - 1, text]
                col += 1
            current = next(cells, None)
        grid.append(row_out)
    return grid


def parse_schedule2_bands(html: str) -> ParseResult:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find_all("table")[0]  # Schedule 2's score matrix; the
    # second table on this page is an unrelated exemption-countries list.
    grid = _flatten_rowspan_grid(table.find_all("tr"))

    # Row 0: decorative/empty. Row 1: "Item | Level of English | Column1..9"
    # (Item/Level rowspan into row 2). Row 2: the 9 test names, in column
    # order — the only place the test names are stated.
    test_names = grid[2][2:]

    # Group every (band, skill) row's per-test cells by (band, test),
    # since C7's grain is per-test-per-band, not per-skill.
    combined: dict[tuple[str, str], dict[str, str]] = {}
    excluded: set[tuple[str, str]] = set()
    skipped = 0

    for row in grid[3:]:
        band = row[1]
        for test_name, cell in zip(test_names, row[2:]):
            key = (band, test_name)
            if cell == "Excluded.":
                excluded.add(key)
                continue
            match = _SKILL_SCORE_RE.match(cell)
            if match is None:
                skipped += 1
                continue
            score, skill = match.group(1), match.group(2).lower()
            combined.setdefault(key, {})[skill] = score

    rows: list[EnglishTestBandRow] = []
    for (band, test_name), skills in combined.items():
        if (band, test_name) in excluded:
            continue
        if set(skills) != set(_SKILL_ORDER):
            skipped += 1
            continue
        description = ", ".join(
            f"{skill.capitalize()} {skills[skill]}" for skill in _SKILL_ORDER
        )
        rows.append(
            EnglishTestBandRow(
                test_name=test_name, band_level=band,
                score_requirement=description,
                points_awarded=POINTS_BY_BAND[band],
            )
        )

    logger.info(
        "english_test_bands: schedule 2 - %d rows, %d excluded combinations, %d skipped",
        len(rows), len(excluded), skipped,
    )
    return ParseResult(rows=rows, skipped=skipped)


_SCORE_COLUMN_LABELS = ("Average band score", "Overall band score", "Total band score")


def parse_functional_english_bands(html: str) -> ParseResult:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find_all("table")[0]
    trs = table.find_all("tr")

    rows: list[EnglishTestBandRow] = []
    skipped = 0
    # Row 0: "Column 1..4" placeholder header. Row 1: real header
    # ("Item", "Language Tests", then the three score-type labels).
    # Rows 2 onward: one test per row, exactly one score column filled.
    for tr in trs[2:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) != 5:
            skipped += 1
            continue
        _item, test_name, average, overall, total = cells
        if not test_name:
            continue  # trailing blank row
        populated = [
            (label, value)
            for label, value in zip(_SCORE_COLUMN_LABELS, (average, overall, total))
            if value
        ]
        if len(populated) != 1:
            skipped += 1
            continue
        label, value = populated[0]
        rows.append(
            EnglishTestBandRow(
                test_name=test_name, band_level="Functional",
                score_requirement=f"{label}: {value}",
                points_awarded=POINTS_BY_BAND["Functional"],
            )
        )

    logger.info("english_test_bands: functional english - %d rows, %d skipped", len(rows), skipped)
    return ParseResult(rows=rows, skipped=skipped)
