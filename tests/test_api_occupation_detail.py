import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from koshi.db import get_session
from koshi.main import app
from koshi.models.ceiling_usage import CeilingUsage
from koshi.models.occupation_momentum import OccupationMomentum
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


def test_shipped_ceiling_seed_loads_cleanly_and_serves_without_404(db_session, client):
    """The shipped seed file must always parse, and a fresh install must
    serve 200 with null ceiling fields rather than 404.

    History: this test used to assert the two rows the seed file shipped
    (261313 → 3200/5000, 254499 → 1800/4000). The 2026-08-17 source audit
    established those values cited a page that does not contain them —
    per-occupation ceilings are not published at the 6-digit grain this
    table needs — so the seed file is now intentionally empty and those
    assertions are gone with the data.

    What remains here is the half of Fix 5 that still applies: a fresh
    install following the README must not 404. The other half — that
    seed_ceiling_usage actually *persists* what the loader produces — is
    covered against a fixture seed file by
    test_seed_ceiling_usage_persists_rows in test_ceiling_seed_loader.py,
    which does not depend on the shipped file carrying data.
    """
    db_session.add(
        Occupation(
            code="261313", name="Software Engineer", unit_group="2613",
            source_url="https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco",
            retrieved_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()

    # Must not raise: guards against a malformed re-population of the file.
    new_rows = seed_ceiling_usage(db_session, CEILING_USAGE_SEED_PATH)
    assert new_rows == [], (
        "the shipped ceiling seed is intentionally empty — see the file header. "
        "If you re-populated it from a real source, update this test."
    )

    response = client.get("/v1/occupations/261313")

    assert response.status_code == 200
    body = response.json()
    assert body["ceiling_issued"] is None
    assert body["ceiling_cap"] is None
    assert body["places_left"] is None


def test_get_occupation_momentum_carries_reliability_tier_and_computed_at(db_session, client):
    """Fix 7: OccupationMomentum already stores reliability_tier="derived"
    and computed_at — the API must not discard that provenance and expose
    momentum as a bare direction string, since the design spec requires
    every fact (computed or scraped) to carry provenance to the client."""
    _seed(db_session)
    computed_at = dt.datetime(2026, 8, 5, 12, 0, tzinfo=dt.timezone.utc)
    db_session.add(
        OccupationMomentum(
            occupation_code="261313", computed_at=computed_at,
            direction="rising", reliability_tier="derived",
        )
    )
    db_session.commit()

    response = client.get("/v1/occupations/261313")

    assert response.status_code == 200
    momentum = response.json()["momentum"]
    assert momentum["value"] == "rising"
    assert momentum["reliability_tier"] == "derived"
    # Compare as instants, not string reprs: Postgres round-trips
    # TIMESTAMP WITH TIME ZONE through the session's local offset rather
    # than preserving UTC's "+00:00" literally.
    assert dt.datetime.fromisoformat(momentum["computed_at"]) == computed_at
