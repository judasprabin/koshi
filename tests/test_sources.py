"""Tests for the sources.py registry (P0.5 / structural-review.md Problem 2).

This is a single source of truth for URL + metadata per built source — a
plain dataclass registry, deliberately not the deferred Control Plane (no
Postgres tables, no acquisition layer). These tests exist so a future sync
module that forgets to route its URL through the registry, or a registry
entry that drifts from the real URL constant, fails loudly instead of
silently.
"""
from koshi import sources


def test_all_lists_every_built_source():
    # One entry per source actually wired into python -m koshi today.
    # If this count changes, either a source was added (update ALL) or
    # removed (same).
    assert len(sources.ALL) == 8


def test_every_source_has_required_fields():
    for source in sources.ALL:
        assert source.key, f"{source} missing key"
        assert source.url.startswith("https://"), f"{source.key} has a non-https url"
        assert source.domain, f"{source.key} missing domain"
        assert source.domain in source.url, (
            f"{source.key}: domain {source.domain!r} not found in url {source.url!r}"
        )
        assert source.category, f"{source.key} missing category"
        assert source.tier, f"{source.key} missing tier"
        assert source.feeds, f"{source.key} missing feeds"
        assert source.cadence, f"{source.key} missing cadence"


def test_keys_are_unique():
    keys = [s.key for s in sources.ALL]
    assert len(keys) == len(set(keys))


def test_source_is_frozen():
    # Sources are shared, imported-by-reference config; mutation from one
    # call site must not leak into another.
    import dataclasses
    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        sources.ANZSCO_OCCUPATIONS.url = "https://example.com"


def test_named_sources_are_all_present_in_ALL():
    named = {
        sources.ANZSCO_OCCUPATIONS, sources.ABS_ANZSCO, sources.LIN19051,
        sources.SKILLSELECT_ROUNDS, sources.SKILLSELECT_PREVIOUS_ROUNDS,
        sources.POINTS_CRITERIA, sources.PROGRAM_ALLOCATION, sources.BP0068,
    }
    assert named == set(sources.ALL)
