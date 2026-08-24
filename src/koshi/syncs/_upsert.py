"""Shared select-by-key / insert-or-update-if-changed helper (issue #4).

points_criteria.py, program_allocation.py, and bp0068.py's
application_funnel upsert each wrote this loop out by hand, identically
— extracted once there were three real examples to compare, rather than
guessing the shape from two (see #4's own comment history).

Deliberately not used everywhere: occupation_list_membership (3-column
key, per-row FK-skip, "membership never changes once recorded" — no
update branch at all), skills_priority (per-jurisdiction unpivot before
any upsert), and skillselect_summary (three independent tables per
call) each have real structural differences this shape doesn't fit
without enough extra parameters to defeat the point of sharing code at
all. A prefixed underscore module name signals this is sync-internal
infrastructure, not part of koshi.syncs.* 's public one-function-per-
source surface.
"""

import datetime as dt
from typing import Any, Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


def upsert_by_key(
    session: Session,
    model: type[ModelT],
    *,
    key: dict[str, Any],
    values: dict[str, Any],
    retrieved_at: dt.datetime,
    build: Callable[[], ModelT],
) -> tuple[ModelT, bool]:
    """Find one row of `model` matching `key`; insert via `build()` if
    none exists, or update `values` in place (and bump `retrieved_at`)
    if any of them actually differ from the current row.

    Returns `(row, written)` — `written` is True iff this call inserted
    a new row or changed an existing one, matching the "only report what
    actually changed" contract every sync in this codebase already
    follows.

    `build()` is only ever called on the insert path — never to
    re-construct a row that already exists, since it may be a closure
    doing real (if cheap) construction work for each candidate row.
    """
    filters = [getattr(model, col) == val for col, val in key.items()]
    existing = session.scalar(select(model).where(*filters))
    if existing is None:
        record = build()
        session.add(record)
        return record, True

    changed = False
    for col, val in values.items():
        if getattr(existing, col) != val:
            setattr(existing, col, val)
            changed = True
    if changed:
        existing.retrieved_at = retrieved_at
    return existing, changed
