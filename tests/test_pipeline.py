import datetime as dt

import httpx

from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupations import Occupation
from koshi.pipeline import sync_anzsco_occupations, sync_skillselect_rounds

ANZSCO_FIXTURE = b"""
<table id="occupation-list">
  <thead><tr><th>ANZSCO Code</th><th>Occupation</th><th>Unit Group</th></tr></thead>
  <tbody>
    <tr><td>261313</td><td>Software Engineer</td><td>2613 Software and Applications Programmers</td></tr>
  </tbody>
</table>
"""

ROUNDS_FIXTURE = b"""
<p>Round date: 24 July 2026</p>
<table id="round-results">
  <thead><tr><th>Occupation</th><th>Points Threshold</th><th>Invitations Issued</th></tr></thead>
  <tbody>
    <tr><td>261313</td><td>85</td><td>120</td></tr>
  </tbody>
</table>
"""

# Same round data as ROUNDS_FIXTURE, but different page bytes (a build
# stamp) — this changes the source_pages content_hash so `changed` is True
# again, even though the underlying round is identical.
ROUNDS_FIXTURE_REPUBLISHED = b"""
<!-- build 20260725-002 -->
<p>Round date: 24 July 2026</p>
<table id="round-results">
  <thead><tr><th>Occupation</th><th>Points Threshold</th><th>Invitations Issued</th></tr></thead>
  <tbody>
    <tr><td>261313</td><td>85</td><td>120</td></tr>
  </tbody>
</table>
"""


def _client_returning(body: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_sync_anzsco_occupations_persists_on_first_run(db_session):
    result = sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))

    assert len(result) == 1
    found = db_session.get(Occupation, "261313")
    assert found.name == "Software Engineer"


def test_sync_anzsco_occupations_is_a_noop_when_page_is_unchanged(db_session):
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))

    result = sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))

    assert result == []  # source_pages saw no content change — nothing re-parsed


def test_sync_skillselect_rounds_persists_on_first_run(db_session):
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))  # occupation FK target

    result = sync_skillselect_rounds(db_session, client=_client_returning(ROUNDS_FIXTURE))

    assert len(result) == 1
    found = db_session.query(EoiRound).filter_by(occupation_code="261313").one()
    assert found.threshold_points == 85


def test_sync_skillselect_rounds_dedups_when_page_hash_changes_but_round_is_identical(db_session):
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))
    sync_skillselect_rounds(db_session, client=_client_returning(ROUNDS_FIXTURE))

    # Page content changed (new content_hash -> changed=True) but the
    # round itself (visa_code, occupation_code, round_date) is identical.
    result = sync_skillselect_rounds(
        db_session, client=_client_returning(ROUNDS_FIXTURE_REPUBLISHED)
    )

    assert result == []  # no new rows were created
    rows = (
        db_session.query(EoiRound)
        .filter_by(occupation_code="261313", round_date=dt.date(2026, 7, 24))
        .all()
    )
    assert len(rows) == 1
