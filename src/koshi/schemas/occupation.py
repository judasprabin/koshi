import datetime as dt

from pydantic import BaseModel


class SourcedFact(BaseModel):
    value: int
    reliability_tier: str
    retrieved_at: dt.datetime
    source_url: str


class DerivedFact(BaseModel):
    """A fact koshi computed itself from its own stored data (design spec
    §3.3), rather than one scraped/curated from an external source — no
    source_url, but still carries reliability_tier + a timestamp so the
    client can visually distinguish it from a SourcedFact."""

    value: str
    reliability_tier: str
    computed_at: dt.datetime


class OccupationProfile(BaseModel):
    code: str
    name: str
    unit_group: str
    # Nullable: an occupation can exist (found by code) with no
    # CeilingUsage row yet — a data gap, not a missing resource, so the
    # endpoint returns 200 with these null rather than 404ing (Fix 6).
    ceiling_issued: SourcedFact | None
    ceiling_cap: SourcedFact | None
    places_left: int | None
    latest_threshold: SourcedFact | None
    momentum: DerivedFact | None
    insight: str | None


class OccupationListItem(BaseModel):
    code: str
    name: str
    momentum: str | None
