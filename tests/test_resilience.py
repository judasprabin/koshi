import datetime as dt
import time

import pytest

from koshi.models.occupations import Occupation
from koshi.resilience import Throttler, isolated_item, parse_int_loose


def test_parse_int_loose_parses_plain_digit_string():
    assert parse_int_loose("120") == 120


def test_parse_int_loose_strips_thousands_separator():
    assert parse_int_loose("1,234") == 1234


def test_parse_int_loose_maps_placeholder_tokens_to_none():
    assert parse_int_loose("N/A") is None
    assert parse_int_loose("-") is None
    assert parse_int_loose("") is None


def test_parse_int_loose_raises_on_garbage():
    with pytest.raises(ValueError):
        parse_int_loose("not a number")


def test_isolated_item_lets_the_session_continue_after_a_failure(db_session):
    with isolated_item(db_session, "bad row"):
        raise ValueError("boom")

    db_session.add(
        Occupation(
            code="999991",
            name="Still Works",
            unit_group="test",
            source_url="https://example.gov.au",
            retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()

    found = db_session.get(Occupation, "999991")
    assert found is not None


def test_isolated_item_persists_successful_work(db_session):
    with isolated_item(db_session, "good row"):
        db_session.add(
            Occupation(
                code="999992",
                name="Good Row",
                unit_group="test",
                source_url="https://example.gov.au",
                retrieved_at=dt.datetime.now(dt.timezone.utc),
                reliability_tier="official_scraped",
            )
        )
    db_session.commit()

    found = db_session.get(Occupation, "999992")
    assert found is not None


def test_throttler_waits_at_least_min_interval_between_calls():
    throttler = Throttler(min_interval_seconds=0.05)
    throttler.wait()
    start = time.monotonic()
    throttler.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.05
