"""Parser for the SkillSelect page's Tables A/C/D — round totals, the
monthly invitation matrix, and state/territory nominations.

Issue #25. Same hidden-field JSON as `skillselect_rounds.py`'s Table B
(occupation minimum scores), but three tables that page never touched:

    A. "Invitations issued on <date>"                — round totals,
       in the "Current round" block.
    C. "Total invitations issued during <year>
       program year"                                 — monthly matrix,
       same block as A.
    D. "State and Territory nominations" block's own
       table, with a reporting-period sentence
       ("...from <date> to <date>.")                 — per-state
       nomination counts, **privacy-suppressed**
       ("<5") for small cells, same idea as BP0068's
       masked negative counts — stored as-published,
       not guessed at.

None of these fit any table in the 22-table catalog
(`docs/superpowers/research/2026-08-16-koshi-data-model.md`) — they're a
genuinely new fact shape, confirmed against the live page rather than
assumed. Each section is parsed independently: a shape problem in one
(Table A/C's block missing, Table D's block missing) degrades that
section to an empty result rather than failing the whole page, since they
now feed three unrelated tables.

Different *streams* of the same 3-digit subclass appear across these
tables with different qualifier text (e.g. subclass 491 is "– Family
Sponsored" in Table C but "State and Territory Nominated" in Table D) —
`visa_label` (the full raw text) is what actually identifies a row;
`visa_code` alone would silently collapse two different things.
"""

import dataclasses
import datetime as dt
import logging
import re

from bs4 import BeautifulSoup

from koshi.extraction.homeaffairs import (
    HiddenFieldError,
    decode_hidden_field_items,
    find_table_after_heading,
)

logger = logging.getLogger(__name__)

JSON_ROOT_KEY = "content"
CURRENT_ROUND_BLOCK_TEXT = "Current round"
STATE_NOMINATIONS_BLOCK_TEXT = "State and Territory nominations"
ROUND_TOTALS_HEADING = "Invitations issued on"
MONTHLY_MATRIX_HEADING = "Total invitations issued during"

_SUBCLASS_RE = re.compile(r"subclass\s+(\d{3})", re.I)
_ROUND_DATE_RE = re.compile(r"invitations issued on\s+(\d{1,2}\s+\w+\s+\d{4})", re.I)
_PROGRAM_YEAR_RE = re.compile(r"(\d{4}-\d{2})\s*program year", re.I)
_PERIOD_RE = re.compile(
    r"from\s+(\d{1,2}\s+\w+\s+\d{4})\s+to\s+(\d{1,2}\s+\w+\s+\d{4})", re.I
)
_STATE_CODES = ("ACT", "NSW", "NT", "Qld", "SA", "Tas", "Vic", "WA")


@dataclasses.dataclass
class RoundTotalRow:
    visa_code: str | None
    visa_label: str
    round_date: dt.date
    total_invited: int
    tie_break_date: str


@dataclasses.dataclass
class MonthlyInvitationRow:
    visa_code: str | None
    visa_label: str
    program_year: str
    month: str
    invited_count: int


@dataclasses.dataclass
class StateNominationRow:
    visa_code: str | None
    visa_label: str
    state_code: str
    period_start: dt.date
    period_end: dt.date
    nominated_count: int | None
    suppressed: bool


@dataclasses.dataclass
class ParseResult:
    round_totals: list[RoundTotalRow]
    monthly_invitations: list[MonthlyInvitationRow]
    state_nominations: list[StateNominationRow]
    skipped: int


def _extract_code(label: str) -> str | None:
    match = _SUBCLASS_RE.search(label)
    return match.group(1) if match else None


def _parse_int_with_commas(text: str) -> int | None:
    cleaned = text.strip().replace(",", "")
    if not cleaned.lstrip("-").isdigit():
        return None
    return int(cleaned)


def _parse_prose_date(text: str) -> dt.date:
    return dt.datetime.strptime(text.strip(), "%d %B %Y").date()


def parse_skillselect_summary(
    page_html: str, *, root_key: str = JSON_ROOT_KEY
) -> ParseResult:
    items = decode_hidden_field_items(page_html, root_key=root_key)
    skipped = 0

    round_totals: list[RoundTotalRow] = []
    monthly_invitations: list[MonthlyInvitationRow] = []
    current_round_block = next(
        (i["block"] for i in items if i.get("text") == CURRENT_ROUND_BLOCK_TEXT and "block" in i),
        None,
    )
    if current_round_block is not None:
        rt, mi, s = _parse_current_round_block(current_round_block)
        round_totals, monthly_invitations = rt, mi
        skipped += s
    else:
        logger.warning(
            "skillselect_summary: no %r block found - round totals and "
            "monthly matrix skipped for this run",
            CURRENT_ROUND_BLOCK_TEXT,
        )

    state_nominations: list[StateNominationRow] = []
    state_block = next(
        (i["block"] for i in items if i.get("text") == STATE_NOMINATIONS_BLOCK_TEXT and "block" in i),
        None,
    )
    if state_block is not None:
        state_nominations, s = _parse_state_nominations_block(state_block)
        skipped += s
    else:
        logger.warning(
            "skillselect_summary: no %r block found - state nominations "
            "skipped for this run",
            STATE_NOMINATIONS_BLOCK_TEXT,
        )

    logger.info(
        "skillselect_summary: %d round totals, %d monthly rows, %d state "
        "nomination rows (%d skipped)",
        len(round_totals), len(monthly_invitations), len(state_nominations), skipped,
    )
    return ParseResult(
        round_totals=round_totals,
        monthly_invitations=monthly_invitations,
        state_nominations=state_nominations,
        skipped=skipped,
    )


def _parse_current_round_block(
    block_html: str,
) -> tuple[list[RoundTotalRow], list[MonthlyInvitationRow], int]:
    skipped = 0
    round_totals: list[RoundTotalRow] = []
    monthly_invitations: list[MonthlyInvitationRow] = []

    try:
        totals_table = find_table_after_heading(block_html, heading_contains=ROUND_TOTALS_HEADING)
    except HiddenFieldError:
        logger.warning("skillselect_summary: round-totals table not found")
    else:
        soup = BeautifulSoup(block_html, "lxml")
        heading = next(
            (h for h in soup.find_all(["h2", "h3", "h4"])
             if ROUND_TOTALS_HEADING.casefold() in h.get_text(strip=True).casefold()),
            None,
        )
        round_date = None
        if heading is not None:
            match = _ROUND_DATE_RE.search(heading.get_text(strip=True))
            if match:
                round_date = _parse_prose_date(match.group(1))
        if round_date is None:
            skipped += 1
        else:
            for tr in totals_table.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if len(cells) != 3 or cells[0].name == "th":
                    continue
                label = cells[0].get_text(strip=True)
                total = _parse_int_with_commas(cells[1].get_text(strip=True))
                if total is None:
                    skipped += 1
                    continue
                round_totals.append(
                    RoundTotalRow(
                        visa_code=_extract_code(label),
                        visa_label=label,
                        round_date=round_date,
                        total_invited=total,
                        tie_break_date=cells[2].get_text(strip=True),
                    )
                )

    try:
        matrix_table = find_table_after_heading(block_html, heading_contains=MONTHLY_MATRIX_HEADING)
    except HiddenFieldError:
        logger.warning("skillselect_summary: monthly-matrix table not found")
    else:
        soup = BeautifulSoup(block_html, "lxml")
        heading = next(
            (h for h in soup.find_all(["h2", "h3", "h4"])
             if MONTHLY_MATRIX_HEADING.casefold() in h.get_text(strip=True).casefold()),
            None,
        )
        program_year = None
        if heading is not None:
            match = _PROGRAM_YEAR_RE.search(heading.get_text(strip=True))
            if match:
                program_year = match.group(1)
        if program_year is None:
            skipped += 1
        else:
            rows = matrix_table.find_all("tr")
            if not rows:
                skipped += 1
            else:
                header_cells = rows[0].find_all(["th", "td"])
                months = [c.get_text(strip=True) for c in header_cells[1:]]
                for tr in rows[1:]:
                    cells = tr.find_all(["td", "th"])
                    if len(cells) != len(months) + 1:
                        skipped += 1
                        continue
                    label = cells[0].get_text(strip=True)
                    code = _extract_code(label)
                    for month, cell in zip(months, cells[1:]):
                        count = _parse_int_with_commas(cell.get_text(strip=True))
                        if count is None:
                            skipped += 1
                            continue
                        monthly_invitations.append(
                            MonthlyInvitationRow(
                                visa_code=code,
                                visa_label=label,
                                program_year=program_year,
                                month=month,
                                invited_count=count,
                            )
                        )

    return round_totals, monthly_invitations, skipped


def _parse_state_nominations_block(
    block_html: str,
) -> tuple[list[StateNominationRow], int]:
    skipped = 0
    rows: list[StateNominationRow] = []

    soup = BeautifulSoup(block_html, "lxml")
    text = soup.get_text()
    period_match = _PERIOD_RE.search(text)
    table = soup.find("table")

    if period_match is None or table is None:
        logger.warning(
            "skillselect_summary: state-nominations table or reporting "
            "period not found"
        )
        return rows, skipped

    period_start = _parse_prose_date(period_match.group(1))
    period_end = _parse_prose_date(period_match.group(2))

    trs = table.find_all("tr")
    if not trs:
        return rows, skipped
    header_cells = trs[0].find_all(["th", "td"])
    states = [c.get_text(strip=True) for c in header_cells[1:]]

    for tr in trs[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) != len(states) + 1:
            skipped += 1
            continue
        label = cells[0].get_text(strip=True)
        code = _extract_code(label)
        for state_code, cell in zip(states, cells[1:]):
            raw = cell.get_text(strip=True)
            if raw.startswith("<"):
                # Privacy suppression (e.g. "<5") — a real published
                # value, not a parse failure. Stored as null + a flag
                # rather than guessing at a number.
                rows.append(
                    StateNominationRow(
                        visa_code=code, visa_label=label, state_code=state_code,
                        period_start=period_start, period_end=period_end,
                        nominated_count=None, suppressed=True,
                    )
                )
                continue
            count = _parse_int_with_commas(raw)
            if count is None:
                skipped += 1
                continue
            rows.append(
                StateNominationRow(
                    visa_code=code, visa_label=label, state_code=state_code,
                    period_start=period_start, period_end=period_end,
                    nominated_count=count, suppressed=False,
                )
            )

    return rows, skipped
