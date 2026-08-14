import datetime as dt

VALID_RELIABILITY_TIERS = {"official_scraped", "official_curated", "derived"}


class ProvenanceError(ValueError):
    """Raised when a fact-bearing row would be inserted without the
    provenance the design spec §3 requires."""


def require_provenance(
    *,
    reliability_tier: str,
    source_url: str | None,
    retrieved_at: dt.datetime | None = None,
) -> None:
    if reliability_tier not in VALID_RELIABILITY_TIERS:
        raise ProvenanceError(
            f"reliability_tier={reliability_tier!r} is not one of {sorted(VALID_RELIABILITY_TIERS)!r}"
        )

    if reliability_tier == "derived":
        return

    if not source_url:
        raise ProvenanceError(
            f"reliability_tier={reliability_tier!r} requires a non-empty source_url"
        )

    if retrieved_at is None:
        raise ProvenanceError(
            f"reliability_tier={reliability_tier!r} requires a retrieved_at datetime"
        )
    if not isinstance(retrieved_at, dt.datetime):
        raise ProvenanceError(f"retrieved_at must be a datetime, got {retrieved_at!r}")

    now = dt.datetime.now(retrieved_at.tzinfo) if retrieved_at.tzinfo else dt.datetime.now()
    if retrieved_at > now:
        raise ProvenanceError(f"retrieved_at {retrieved_at!r} is in the future")
