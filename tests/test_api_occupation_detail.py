import datetime as dt

import pytest
from fastapi.testclient import TestClient

from koshi.db import get_session
from koshi.main import app
from koshi.models.ceiling_usage import CeilingUsage
from koshi.models.occupations import Occupation


@pytest.fixture()
def client(db_session):
    """TestClient with get_session overridden to the test db_session.

    Uses try/finally so the override is cleared even if a test assertion
    fails partway through — an uncleared override would leak into other
    tests' TestClient calls (e.g. Task 12's) since `app` is a module-level
    singleton shared across the whole test session.
    """
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed(db_session):
    # Occupation must be committed before CeilingUsage: there's no ORM
    # relationship() between the two models (only a raw ForeignKey column),
    # so SQLAlchemy's unit-of-work flush ordering can't be relied on to
    # insert occupations before ceiling_usage within a single commit.
    db_session.add(
        Occupation(
            code="261313", name="Software Engineer", unit_group="2613",
            source_url="https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco",
            retrieved_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()
    db_session.add(
        CeilingUsage(
            occupation_code="261313", program_year="2025-26", issued=3200, ceiling=5000,
            as_of_date=dt.date(2026, 7, 31),
            source_url="https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels",
            retrieved_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
            reliability_tier="official_curated",
        )
    )
    db_session.commit()


def test_get_occupation_returns_profile_with_provenance(db_session, client):
    _seed(db_session)

    response = client.get("/v1/occupations/261313")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "261313"
    assert body["places_left"] == 1800
    assert body["ceiling_issued"]["reliability_tier"] == "official_curated"
    assert body["ceiling_issued"]["source_url"].startswith("https://immi.homeaffairs.gov.au")
    assert "1800" in body["insight"]
    assert body["momentum"] is None  # fewer than 3 eoi_rounds seeded


def test_get_occupation_404_for_unknown_code(client):
    response = client.get("/v1/occupations/999999")

    assert response.status_code == 404
