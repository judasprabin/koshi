import datetime as dt

import pytest

from koshi.provenance import ProvenanceError, require_provenance


def test_derived_tier_does_not_require_source_url():
    require_provenance(reliability_tier="derived", source_url=None)  # must not raise


def test_official_scraped_requires_source_url():
    with pytest.raises(ProvenanceError):
        require_provenance(reliability_tier="official_scraped", source_url=None)


def test_official_curated_requires_non_empty_source_url():
    with pytest.raises(ProvenanceError):
        require_provenance(reliability_tier="official_curated", source_url="")


def test_unrecognized_reliability_tier_is_rejected():
    # A typo like "offical_scraped" must not silently pass provenance.
    with pytest.raises(ProvenanceError):
        require_provenance(
            reliability_tier="offical_scraped",
            source_url="https://example.gov.au",
            retrieved_at=dt.datetime.now(dt.timezone.utc),
        )


def test_future_retrieved_at_is_rejected():
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    with pytest.raises(ProvenanceError):
        require_provenance(
            reliability_tier="official_scraped",
            source_url="https://example.gov.au",
            retrieved_at=future,
        )


def test_missing_retrieved_at_is_rejected_for_non_derived_tier():
    with pytest.raises(ProvenanceError):
        require_provenance(
            reliability_tier="official_scraped",
            source_url="https://example.gov.au",
            retrieved_at=None,
        )
