import datetime as dt

from pydantic import BaseModel


class SourcedFact(BaseModel):
    value: int
    reliability_tier: str
    retrieved_at: dt.datetime
    source_url: str


class OccupationProfile(BaseModel):
    code: str
    name: str
    unit_group: str
    ceiling_issued: SourcedFact
    ceiling_cap: SourcedFact
    places_left: int
    latest_threshold: SourcedFact | None
    momentum: str | None
    insight: str


class OccupationListItem(BaseModel):
    code: str
    name: str
    momentum: str | None
