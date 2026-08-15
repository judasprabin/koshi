import datetime as dt

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import koshi.pipeline as pipeline_module
from koshi.db import Base
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupation_momentum import OccupationMomentum
from koshi.models.occupations import Occupation
from koshi.models.source_pages import SourcePage
from koshi.pipeline import SKILLSELECT_ROUNDS_URL, sync_anzsco_occupations, sync_skillselect_rounds

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

# No "Round date: ..." text — parse_skillselect_rounds raises ValueError.
BROKEN_ROUNDS_FIXTURE = b"""
<table id="round-results">
  <thead><tr><th>Occupation</th><th>Points Threshold</th><th>Invitations Issued</th></tr></thead>
  <tbody>
    <tr><td>261313</td><td>85</td><td>120</td></tr>
  </tbody>
</table>
"""

# Same (visa_code, occupation_code, round_date) key appears twice within a
# single page — a real possibility in messy government HTML tables — to
# reproduce the in-batch duplicate crash (Fix B).
ROUNDS_FIXTURE_WITH_IN_BATCH_DUPLICATE = b"""
<p>Round date: 24 July 2026</p>
<table id="round-results">
  <thead><tr><th>Occupation</th><th>Points Threshold</th><th>Invitations Issued</th></tr></thead>
  <tbody>
    <tr><td>261313</td><td>85</td><td>120</td></tr>
    <tr><td>261313</td><td>85</td><td>120</td></tr>
  </tbody>
</table>
"""


def _client_returning(body: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture()
def db_session_no_autoflush(engine):
    # Mirrors koshi.db.SessionLocal's exact settings (autoflush=False,
    # autocommit=False) — tests/conftest.py's shared `db_session` fixture
    # uses sessionmaker's default autoflush=True, which would flush each
    # session.add() before the next iteration's SELECT and mask the
    # in-batch duplicate bug entirely. Constructed deliberately here so
    # this stays a real regression test for the production session's
    # behaviour rather than the test suite's.
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    yield session
    session.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()


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


def test_parse_failure_does_not_advance_extraction_watermark(db_session):
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))

    with pytest.raises(ValueError):
        sync_skillselect_rounds(db_session, client=_client_returning(BROKEN_ROUNDS_FIXTURE))

    page = db_session.query(SourcePage).filter_by(url=SKILLSELECT_ROUNDS_URL).one()
    assert page.last_extracted_at is None
    assert db_session.query(EoiRound).count() == 0


def test_sync_retries_parse_after_a_previous_failure(db_session):
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))

    with pytest.raises(ValueError):
        sync_skillselect_rounds(db_session, client=_client_returning(BROKEN_ROUNDS_FIXTURE))

    # Same broken content again: fetch_and_register will report
    # changed=False (the hash hasn't moved since the failed attempt), but
    # the sync must still attempt to parse — not silently no-op — because
    # last_extracted_at was never advanced past last_changed_at.
    with pytest.raises(ValueError):
        sync_skillselect_rounds(db_session, client=_client_returning(BROKEN_ROUNDS_FIXTURE))

    # And once the page is republished with valid content, the retry
    # succeeds and the watermark finally advances.
    result = sync_skillselect_rounds(db_session, client=_client_returning(ROUNDS_FIXTURE))
    assert len(result) == 1
    page = db_session.query(SourcePage).filter_by(url=SKILLSELECT_ROUNDS_URL).one()
    assert page.last_extracted_at is not None


def test_sync_skillselect_rounds_dedups_in_batch_duplicate_rows(db_session_no_autoflush):
    # Reproduces the crash under the app's real session settings
    # (autoflush=False, like koshi.db.SessionLocal): without in-batch
    # dedup, both identical rows would pass the "not found in DB" check
    # (session.add() is never flushed before the next SELECT), both would
    # be queued, and the commit would raise an unhandled UniqueViolation —
    # rolling back the whole sync instead of just skipping the duplicate.
    sync_anzsco_occupations(db_session_no_autoflush, client=_client_returning(ANZSCO_FIXTURE))

    result = sync_skillselect_rounds(
        db_session_no_autoflush, client=_client_returning(ROUNDS_FIXTURE_WITH_IN_BATCH_DUPLICATE)
    )

    assert len(result) == 1  # the in-batch duplicate was skipped, not crashed on
    rows = (
        db_session_no_autoflush.query(EoiRound)
        .filter_by(occupation_code="261313", round_date=dt.date(2026, 7, 24))
        .all()
    )
    assert len(rows) == 1  # exactly one row persisted — not zero, not two


def test_momentum_refresh_failure_for_one_code_does_not_block_the_other(db_session, monkeypatch):
    db_session.add_all([
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
    ])
    db_session.commit()

    # Two prior rounds each — the round this test triggers is each
    # occupation's 3rd, completing compute_momentum's trailing-3 window.
    base_date = dt.date(2026, 5, 1)
    for code in ("261313", "254499"):
        for i, points in enumerate([70, 75]):
            db_session.add(
                EoiRound(
                    visa_code="189", occupation_code=code,
                    round_date=base_date + dt.timedelta(days=30 * i),
                    threshold_points=points, invitations_issued=100,
                    source_url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
                    retrieved_at=dt.datetime.now(dt.timezone.utc),
                    reliability_tier="official_scraped",
                )
            )
    db_session.commit()

    fixture = b"""
    <p>Round date: 24 July 2026</p>
    <table id="round-results">
      <thead><tr><th>Occupation</th><th>Points Threshold</th><th>Invitations Issued</th></tr></thead>
      <tbody>
        <tr><td>261313</td><td>85</td><td>120</td></tr>
        <tr><td>254499</td><td>80</td><td>90</td></tr>
      </tbody>
    </table>
    """

    original_refresh_momentum = pipeline_module.refresh_momentum

    def flaky_refresh(session, code):
        if code == "261313":
            raise RuntimeError("simulated momentum failure")
        return original_refresh_momentum(session, code)

    monkeypatch.setattr(pipeline_module, "refresh_momentum", flaky_refresh)

    def handler(request):
        return httpx.Response(200, content=fixture)

    result = pipeline_module.sync_skillselect_rounds(
        db_session, client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    assert len(result) == 2  # both rounds still persisted despite the momentum failure

    working_momentum = db_session.scalar(
        select(OccupationMomentum).where(OccupationMomentum.occupation_code == "254499")
    )
    assert working_momentum is not None
    assert working_momentum.direction == "rising"

    failed_momentum = db_session.scalar(
        select(OccupationMomentum).where(OccupationMomentum.occupation_code == "261313")
    )
    assert failed_momentum is None
