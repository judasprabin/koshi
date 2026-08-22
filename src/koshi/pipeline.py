"""Shared sync helpers, plus the stable import surface for every source.

Per-source sync logic lives in `koshi.syncs.*` (docs/structural-review.md
Problem 1) and URL/metadata registration lives in `koshi.sources`
(Problem 2). This module is now two things only:

1. Helpers genuinely shared by more than one sync module —
   `_needs_extraction`, `_RowsWithSkipCount`, `refresh_momentum_for_codes`,
   `_persist_rounds`, `resolve_round_occupation_codes`. These stay here
   rather than in `koshi.syncs` because moving them there would just
   relocate the god-module problem one level down, and because
   `refresh_momentum_for_codes` must stay a plain module-level name here
   for `tests/test_pipeline.py`'s `monkeypatch.setattr(pipeline_module,
   "refresh_momentum", ...)` to keep intercepting it.
2. A re-export of every `sync_*`/URL name that used to be defined here
   directly, so `koshi.__main__` and existing tests don't need to change
   their imports — only the file each function's *body* lives in moved.

The shared-helper definitions above MUST stay before the `from
koshi.syncs.* import ...` lines below: each syncs module imports these
helpers back from `koshi.pipeline` at its own import time, and Python
resolves that against this module's partially-built namespace — so the
helpers have to already be bound by the time those imports run.
"""
import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crosswalk import resolve_occupation_code
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupations import Occupation
from koshi.models.source_pages import SourcePage
from koshi.momentum import refresh_momentum

logger = logging.getLogger(__name__)


class _RowsWithSkipCount(list):
    """A plain list subclass that additionally carries the extraction
    parser's skip count (ParseResult.skipped).

    sync_anzsco_occupations/sync_skillselect_rounds's return type
    (list[Occupation]/list[EoiRound]) is relied on elsewhere (e.g.
    tests/test_pipeline.py) and must not change. Since it's still a real
    list, every existing caller (len(), iteration, `== []`, ...) keeps
    working unmodified; __main__.py's run summary can additionally read
    the bonus `.skipped` attribute via getattr(result, "skipped", None)
    to surface how many rows a run silently dropped, without either side
    needing a wider return-type change.
    """

    skipped: int = 0


# A stand-in for "never extracted" that compares less than any real
# last_changed_at, so a page with no last_extracted_at watermark always
# looks due for extraction.
_NEVER_EXTRACTED = dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _needs_extraction(page: SourcePage) -> bool:
    """Whether this page's content has changed since it was last
    successfully parsed.

    Deliberately NOT the `changed` bool fetch_and_register returns:
    fetch_and_register commits content_hash/last_changed_at before parsing
    is even attempted, so if parsing raised last time, `changed` would be
    False on the next run (the hash hasn't moved) and the page would be
    silently skipped forever. Comparing last_changed_at against our own
    last_extracted_at watermark instead means a prior parse failure (which
    leaves last_extracted_at untouched) is retried on every subsequent run.
    """
    watermark = page.last_extracted_at or _NEVER_EXTRACTED
    return page.last_changed_at > watermark


def refresh_momentum_for_codes(session: Session, codes: set[str]) -> None:
    """Recompute momentum for each occupation code, isolated per code.

    Nothing else in the system calls refresh_momentum, so without this
    `occupation_momentum` rows are never produced end-to-end and
    GET /v1/occupations always shows momentum: null.

    One occupation's failure must not prevent the others from refreshing,
    and must not undo work that already committed.
    """
    for code in codes:
        try:
            refresh_momentum(session, code)
        except Exception:
            # Roll back before logging: against the real Postgres-backed
            # session this codebase uses, a genuine DB-level failure
            # (constraint violation, stale row, connection hiccup) leaves
            # the session's transaction deactivated — every subsequent
            # operation on it raises until rollback() runs. Without this,
            # the *next* occupation code's refresh_momentum call would
            # itself raise on the still-poisoned transaction and get
            # logged as a spurious failure, cascading one real failure
            # into every occupation processed afterward.
            session.rollback()
            logger.exception("momentum refresh failed for occupation_code=%s", code)


def _persist_rounds(session: Session, rounds: list[EoiRound]) -> list[EoiRound]:
    """Insert rounds not already stored, deduping within the batch too.

    Shared by the current-round and previous-rounds syncs, which overlap:
    a round can appear on both pages. Keyed on
    (visa_code, occupation_name_raw, round_date) — the name, not the code,
    because an unresolved row's code is NULL and Postgres treats NULLs as
    distinct, which would defeat the check entirely.

    The in-batch `staged_keys` set is required because the production
    session runs autoflush=False: an earlier session.add() is not flushed
    before the next iteration's SELECT, so two identical rows in one page
    would both pass the DB check and collide at commit.
    """
    new_rounds: list[EoiRound] = []
    staged_keys: set[tuple[str, str, dt.date]] = set()
    for round_ in rounds:
        key = (round_.visa_code, round_.occupation_name_raw, round_.round_date)
        if key in staged_keys:
            continue
        existing = session.scalar(
            select(EoiRound).where(
                EoiRound.visa_code == round_.visa_code,
                EoiRound.occupation_name_raw == round_.occupation_name_raw,
                EoiRound.round_date == round_.round_date,
            )
        )
        if existing is not None:
            continue
        session.add(round_)
        staged_keys.add(key)
        new_rounds.append(round_)
    return new_rounds


def resolve_round_occupation_codes(session: Session, rounds: list[EoiRound]) -> int:
    """Fill occupation_code on scraped rounds from the name crosswalk.

    Returns the number resolved. Rows the crosswalk cannot resolve keep
    occupation_code = NULL and their occupation_name_raw, so they stay
    re-resolvable once the crosswalk is extended — an unresolved name is
    recorded as unresolved rather than guessed at.

    A resolved code is only written if it actually exists in `occupations`,
    because `eoi_rounds.occupation_code` is an FK. The crosswalk carries
    codes koshi's occupation table legitimately does not have: LIN 19/051 is
    coded against ANZSCO 2013 (25 of its codes are absent from 2022), and
    the JSA listing koshi loads is 2022. Writing one of those would abort
    the whole batch on a foreign-key violation.
    """
    resolved = 0
    unresolved: list[str] = []
    missing_fk: list[str] = []
    for round_ in rounds:
        if round_.occupation_code is not None:
            continue
        code = resolve_occupation_code(session, round_.occupation_name_raw)
        if code is None:
            unresolved.append(round_.occupation_name_raw)
            continue
        if session.get(Occupation, code) is None:
            missing_fk.append(f"{round_.occupation_name_raw}->{code}")
            continue
        round_.occupation_code = code
        resolved += 1

    logger.info(
        "crosswalk: resolved %d/%d round occupations", resolved, len(rounds)
    )
    if unresolved:
        logger.warning(
            "crosswalk: %d occupation name(s) unresolved, e.g. %r",
            len(unresolved), unresolved[:5],
        )
    if missing_fk:
        logger.warning(
            "crosswalk: %d code(s) resolved but absent from occupations "
            "(edition mismatch?), e.g. %r",
            len(missing_fk), missing_fk[:5],
        )
    return resolved


# --- Re-exports: sync functions now live in koshi.syncs.*; URL constants
# now live in koshi.sources. Both are re-exported here unchanged so
# koshi.__main__ and existing tests import from koshi.pipeline exactly as
# before this split. ---

from koshi.syncs.anzsco import sync_anzsco_occupations  # noqa: E402
from koshi.syncs.abs import sync_abs_occupations  # noqa: E402
from koshi.syncs.occupation_titles import sync_occupation_titles  # noqa: E402
from koshi.syncs.skillselect import sync_skillselect_rounds  # noqa: E402
from koshi.syncs.previous_rounds import sync_skillselect_previous_rounds  # noqa: E402
from koshi.syncs.bp0068 import sync_bp0068_grants  # noqa: E402
from koshi.syncs.backfill import backfill_unresolved_round_codes  # noqa: E402

from koshi.sources import (  # noqa: E402
    ABS_ANZSCO,
    ANZSCO_OCCUPATIONS,
    BP0068,
    LIN19051,
    SKILLSELECT_PREVIOUS_ROUNDS,
    SKILLSELECT_ROUNDS,
)

ANZSCO_URL = ANZSCO_OCCUPATIONS.url
SKILLSELECT_ROUNDS_URL = SKILLSELECT_ROUNDS.url
SKILLSELECT_PREVIOUS_ROUNDS_URL = SKILLSELECT_PREVIOUS_ROUNDS.url
LIN19051_URL = LIN19051.url
BP0068_URL = BP0068.url
ABS_ANZSCO_URL = ABS_ANZSCO.url
