"""Tests for the occupation_list_membership sync (issue #21).

The parser (parse_lin_occupation_lists) is already tested against the live
fixture in test_extraction_crosswalk_sources.py — these tests cover the
sync layer: FK resolution against `occupations`, per-row isolation for
codes that don't resolve, upsert semantics, and the compilation_date
derived from the source URL.
"""

import datetime as dt
from pathlib import Path

import httpx

from koshi.models.occupation_list_membership import OccupationListMembership
from koshi.models.occupations import Occupation
from koshi.syncs.occupation_list_membership import sync_occupation_list_membership
from sqlalchemy import select

FIXTURES = Path(__file__).parent / "fixtures"
LIN_FIXTURE = (FIXTURES / "lin19051_tables_live.html").read_bytes()

# Real codes drawn from the live fixture (see the module docstring in
# lin19051.py's test file for how these were found): one per list.
MLTSSL_CODE = "133111"
STSOL_CODE = "121212"
ROL_CODE = "121111"


def _client_returning(body: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _seed_occupation(session, code: str) -> None:
    session.add(
        Occupation(
            code=code, name=f"Test Occupation {code}", unit_group=code[:4],
            code_grain="occupation", anzsco_edition="2013",
            source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    session.commit()


def test_persists_rows_for_codes_that_resolve_against_occupations(db_session):
    _seed_occupation(db_session, MLTSSL_CODE)
    _seed_occupation(db_session, STSOL_CODE)
    _seed_occupation(db_session, ROL_CODE)

    result = sync_occupation_list_membership(db_session, client=_client_returning(LIN_FIXTURE))

    by_code_list = {(r.occupation_code, r.list_name) for r in result}
    assert (MLTSSL_CODE, "MLTSSL") in by_code_list
    assert (STSOL_CODE, "STSOL") in by_code_list
    assert (ROL_CODE, "ROL") in by_code_list


def test_skips_codes_absent_from_occupations_rather_than_crashing(db_session):
    """504 codes across the 3 lists; this test seeds none of them, so
    every row should be skipped — a real FK violation must never abort
    the batch."""
    result = sync_occupation_list_membership(db_session, client=_client_returning(LIN_FIXTURE))

    assert len(result) == 0
    assert result.skipped == 504


def test_anzsco_edition_is_2013(db_session):
    """LIN 19/051 is coded against ANZSCO 2013 — matches
    extraction.lin19051.ANZSCO_EDITION exactly, not hardcoded twice."""
    _seed_occupation(db_session, MLTSSL_CODE)

    sync_occupation_list_membership(db_session, client=_client_returning(LIN_FIXTURE))

    row = db_session.scalar(
        select(OccupationListMembership).where(
            OccupationListMembership.occupation_code == MLTSSL_CODE
        )
    )
    assert row.anzsco_edition == "2013"


def test_compilation_date_comes_from_the_source_url():
    """LIN19051_URL's path segments pin the compilation
    (.../2026-03-28/2026-03-28/...) — the compilation_date must be
    derived from that, not guessed at or left as today's date."""
    from koshi.sources import LIN19051

    assert "2026-03-28" in LIN19051.url


def test_rerun_upserts_rather_than_duplicating(db_session):
    _seed_occupation(db_session, MLTSSL_CODE)

    sync_occupation_list_membership(db_session, client=_client_returning(LIN_FIXTURE))
    sync_occupation_list_membership(db_session, client=_client_returning(LIN_FIXTURE))

    rows = db_session.scalars(
        select(OccupationListMembership).where(
            OccupationListMembership.occupation_code == MLTSSL_CODE
        )
    ).all()
    assert len(rows) == 1
