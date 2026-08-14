import datetime as dt

import pytest
from fastapi.testclient import TestClient

from koshi.db import get_session
from koshi.main import app
from koshi.models.occupation_momentum import OccupationMomentum
from koshi.models.occupations import Occupation


@pytest.fixture()
def client(db_session):
    """TestClient with get_session overridden to the test db_session.

    Uses try/finally so the override is cleared even if a test assertion
    fails partway through — an uncleared override would leak into other
    tests' TestClient calls since `app` is a module-level singleton shared
    across the whole test session.
    """
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_two_occupations_with_momentum(db_session):
    db_session.add_all(
        [
            Occupation(
                code="261313", name="Software Engineer", unit_group="2613",
                source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
                reliability_tier="official_scraped",
            ),
            Occupation(
                code="254499", name="Registered Nurse (Aged Care)", unit_group="2544",
                source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
                reliability_tier="official_scraped",
            ),
        ]
    )
    db_session.commit()
    db_session.add_all(
        [
            OccupationMomentum(
                occupation_code="254499", computed_at=dt.datetime.now(dt.timezone.utc),
                direction="falling", reliability_tier="derived",
            ),
            OccupationMomentum(
                occupation_code="261313", computed_at=dt.datetime.now(dt.timezone.utc),
                direction="rising", reliability_tier="derived",
            ),
        ]
    )
    db_session.commit()


def test_list_occupations_sortable_by_momentum(db_session, client):
    _seed_two_occupations_with_momentum(db_session)

    response = client.get("/v1/occupations?sort=momentum")

    assert response.status_code == 200
    codes_in_order = [item["code"] for item in response.json()]
    assert codes_in_order == ["261313", "254499"]  # rising ranks before falling


def test_list_occupations_defaults_to_code_order(db_session, client):
    _seed_two_occupations_with_momentum(db_session)

    response = client.get("/v1/occupations")

    codes_in_order = [item["code"] for item in response.json()]
    assert codes_in_order == ["254499", "261313"]  # lexical code order
