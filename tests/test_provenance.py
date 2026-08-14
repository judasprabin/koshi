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
