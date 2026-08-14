class ProvenanceError(ValueError):
    """Raised when a fact-bearing row would be inserted without the
    provenance the design spec §3 requires."""


def require_provenance(*, reliability_tier: str, source_url: str | None) -> None:
    if reliability_tier == "derived":
        return
    if not source_url:
        raise ProvenanceError(
            f"reliability_tier={reliability_tier!r} requires a non-empty source_url"
        )
