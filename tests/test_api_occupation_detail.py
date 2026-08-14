import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from koshi.db import get_session
from koshi.main import app
from koshi.models.ceiling_usage import CeilingUsage
from koshi.models.occupations import Occupation
from koshi.seeds.loader import seed_ceiling_usage

CEILING_USAGE_SEED_PATH = (
    Path(__file__).parent.parent / "src" / "koshi" / "seeds" / "ceiling_usage_manual.yaml"
)


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


def test_get_occupation_returns_200_with_nulls_when_no_ceiling_data_yet(db_session, client):
    """Fix 6: an occupation existing with no CeilingUsage row yet is a data
    gap, not a missing resource — 404 is reserved for an unknown occupation
    code (see test_get_occupation_404_for_unknown_code above)."""
    db_session.add(
        Occupation(
            code="261313", name="Software Engineer", unit_group="2613",
            source_url="https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco",
            retrieved_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()

    response = client.get("/v1/occupations/261313")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "261313"
    assert body["ceiling_issued"] is None
    assert body["ceiling_cap"] is None
    assert body["places_left"] is None
    assert body["insight"] is None
    assert body["momentum"] is None


def test_seeded_ceiling_usage_is_actually_servable_end_to_end(db_session, client):
    """Regression for Fix 5: nothing previously persisted the rows
    load_ceiling_usage_seed produced, so a fresh install following the
    README had no ceiling_usage rows and every occupation 404'd. This seeds
    via seed_ceiling_usage (the real shipped seed file) rather than
    inserting a CeilingUsage row by hand."""
    # The shipped seed file covers both 261313 and 254499 — every occupation
    # code it references must already exist to satisfy ceiling_usage's FK.
    db_session.add_all(
        [
            Occupation(
                code="261313", name="Software Engineer", unit_group="2613",
                source_url="https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco",
                retrieved_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
                reliability_tier="official_scraped",
            ),
            Occupation(
                code="254499", name="Registered Nurse (Aged Care)", unit_group="2544",
                source_url="https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco",
                retrieved_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
                reliability_tier="official_scraped",
            ),
        ]
    )
    db_session.commit()

    new_rows = seed_ceiling_usage(db_session, CEILING_USAGE_SEED_PATH)
    assert len(new_rows) >= 1

    response = client.get("/v1/occupations/261313")

    assert response.status_code == 200
    body = response.json()
    assert body["ceiling_issued"]["value"] == 3200
    assert body["ceiling_cap"]["value"] == 5000
    assert body["places_left"] == 1800
