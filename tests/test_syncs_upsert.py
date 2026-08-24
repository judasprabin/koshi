"""Tests for upsert_by_key (issue #4).

Centralizes the select-by-key / insert-or-update-if-changed loop that
points_criteria.py, program_allocation.py, and bp0068.py's
application_funnel upsert each wrote out by hand, identically, once
there were three real examples to compare rather than guessing the
shape from two.

Tested against PointsCriterion directly — a real model, not a
throwaway test-only one, since it's exactly the shape this helper
targets (2-column key, one value column).
"""

import datetime as dt

from sqlalchemy import select

from koshi.models.points_criteria_reference import PointsCriterion
from koshi.syncs._upsert import upsert_by_key

RETRIEVED_AT = dt.datetime(2026, 8, 24, tzinfo=dt.timezone.utc)


def _build(criterion_name="Age", band_description="18-24 years", points_value=25):
    return PointsCriterion(
        criterion_name=criterion_name, band_description=band_description,
        points_value=points_value, source_url="https://example.gov.au",
        retrieved_at=RETRIEVED_AT, reliability_tier="official_scraped",
    )


def test_inserts_a_new_row_when_no_existing_match(db_session):
    record, written = upsert_by_key(
        db_session, PointsCriterion,
        key={"criterion_name": "Age", "band_description": "18-24 years"},
        values={"points_value": 25},
        retrieved_at=RETRIEVED_AT,
        build=_build,
    )

    assert written is True
    assert record.points_value == 25
    db_session.commit()
    assert db_session.query(PointsCriterion).count() == 1


def test_leaves_an_unchanged_row_alone_and_reports_written_false(db_session):
    db_session.add(_build())
    db_session.commit()

    record, written = upsert_by_key(
        db_session, PointsCriterion,
        key={"criterion_name": "Age", "band_description": "18-24 years"},
        values={"points_value": 25},  # same value
        retrieved_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
        build=_build,
    )

    assert written is False
    assert record.retrieved_at == RETRIEVED_AT  # not bumped — nothing changed


def test_updates_an_existing_row_in_place_when_a_value_changed(db_session):
    db_session.add(_build(points_value=25))
    db_session.commit()

    new_retrieved_at = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    record, written = upsert_by_key(
        db_session, PointsCriterion,
        key={"criterion_name": "Age", "band_description": "18-24 years"},
        values={"points_value": 30},  # changed
        retrieved_at=new_retrieved_at,
        build=_build,
    )
    db_session.commit()

    assert written is True
    assert record.points_value == 30
    assert record.retrieved_at == new_retrieved_at  # bumped — something changed
    assert db_session.query(PointsCriterion).count() == 1  # updated in place, not duplicated


def test_build_is_not_called_when_an_existing_row_matches(db_session):
    """build() may be a closure capturing per-row fetch data (e.g. a
    freshly-parsed row from the current run) — it must never run when
    updating an existing row, since it's only meant to construct a
    brand-new instance. Calling it unconditionally would be wasted work
    at best and, for a build() with side effects, a real bug."""
    db_session.add(_build())
    db_session.commit()

    calls = []

    def tracked_build():
        calls.append(1)
        return _build()

    upsert_by_key(
        db_session, PointsCriterion,
        key={"criterion_name": "Age", "band_description": "18-24 years"},
        values={"points_value": 30},  # changed, so this exercises the update path
        retrieved_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
        build=tracked_build,
    )

    assert calls == []


def test_multiple_changed_values_all_get_applied(db_session):
    db_session.add(_build(points_value=25))
    db_session.commit()

    def build_with_two_fields():
        return PointsCriterion(
            criterion_name="Age", band_description="18-24 years",
            points_value=99, source_url="https://changed.gov.au",
            retrieved_at=RETRIEVED_AT, reliability_tier="official_scraped",
        )

    record, written = upsert_by_key(
        db_session, PointsCriterion,
        key={"criterion_name": "Age", "band_description": "18-24 years"},
        values={"points_value": 30, "source_url": "https://new-source.gov.au"},
        retrieved_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
        build=build_with_two_fields,
    )

    assert written is True
    assert record.points_value == 30
    assert record.source_url == "https://new-source.gov.au"
