import datetime as dt
import html as html_module
import json

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

import koshi.pipeline as pipeline_module
from koshi.db import Base
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupation_momentum import OccupationMomentum
from koshi.models.occupations import Occupation
from koshi.models.occupation_titles import OccupationTitle
from koshi.models.source_pages import SourcePage
from koshi.crosswalk import normalize_title
from koshi.pipeline import SKILLSELECT_ROUNDS_URL, sync_anzsco_occupations, sync_skillselect_rounds

def _anzsco_page(occupations: list[tuple[str, str]], *, last_page: int = 0) -> bytes:
    """Build a page in the real Drupal Views card-grid shape.

    The old fixture here was a synthetic `<table id="occupation-list">`,
    which exists nowhere on the live site. `last_page` drives the pager:
    0 means a single page, so tests that return the same body for every
    request don't loop.
    """
    cards = "".join(
        '<div class="rowc"><a href="/x"><div class="card_inner">'
        f'<div class="card_anzsco">ANZSCO {code}</div>'
        f'<h4 class="card_title">{name}</h4>'
        "</div></a></div>"
        for code, name in occupations
    )
    pager = "".join(
        f'<li class="page-item"><a href="?page={n}" class="page-link">{n + 1}</a></li>'
        for n in range(1, last_page + 1)
    )
    return (
        '<html><body><div class="views-element-container view-occupation-index" '
        'id="block-views-block-occupation-index-block-occupations">'
        f'<div class="view-content row">{cards}</div>'
        + (f"<nav><ul>{pager}</ul></nav>" if pager else "")
        + "</div></body></html>"
    ).encode()


ANZSCO_FIXTURE = _anzsco_page([("261313", "Software Engineer")])

# SkillSelect fixtures are built to the *real* page structure: content is
# entity-encoded JSON inside a hidden input, the occupation table has two
# columns and no <th>, and it is found via its preceding heading. The old
# fixtures here were a synthetic three-column `id="round-results"` table
# that exists nowhere on the live site — which is exactly how the parser
# passed its tests for weeks while extracting zero rows in production.
#
# MIN_OCCUPATION_ROWS guards against a collapsed table, so these fixtures
# must clear it; _rounds_page pads with filler occupations to do so.
def _rounds_page(
    occupations: list[tuple[str, int]],
    *,
    round_date: str = "24 July 2026",
    build_stamp: str = "",
    include_round_heading: bool = True,
) -> bytes:
    rows = "".join(
        f"<tr><td><p>{name}</p></td><td><p>{points}</p></td></tr>"
        for name, points in occupations
    )
    summary = (
        f"<h3>Invitations issued on {round_date}</h3>"
        "<table><thead><tr><th>Visa subclass</th><th>Total EOIs Invited</th>"
        "<th>Tie break date</th></tr></thead>"
        "<tbody><tr><td><p>Skilled Independent visa (subclass 189)</p></td>"
        "<td><p>10,000</p></td><td><p>24/04/2026</p></td></tr></tbody></table>"
        if include_round_heading
        else ""
    )
    block = (
        f"{build_stamp}{summary}"
        "<h3>Invitations issued by occupation and minimum score invited</h3>"
        f"<table><tbody>{rows}</tbody></table>"
    )
    payload = json.dumps({"content": [{"id": "1", "text": "", "block": block}]})
    return (
        '<html><body><input type="hidden" '
        'id="ctl00_PlaceHolderMain_PageSchemaHiddenField_Input" value="'
        + html_module.escape(payload, quote=True)
        + '"></body></html>'
    ).encode()


# 60 rows clears MIN_OCCUPATION_ROWS (50); the first is the one under test.
_FILLER = [(f"Filler Occupation {i}", 60 + i % 20) for i in range(59)]

ROUNDS_FIXTURE = _rounds_page([("Software Engineer", 85), *_FILLER])

# Same round data, different page bytes (a build stamp) — changes the
# source_pages content_hash so `changed` is True again, even though the
# underlying round is identical.
ROUNDS_FIXTURE_REPUBLISHED = _rounds_page(
    [("Software Engineer", 85), *_FILLER], build_stamp="<!-- build 20260725-002 -->"
)

# No "Invitations issued on ..." heading — the parser raises.
BROKEN_ROUNDS_FIXTURE = _rounds_page(
    [("Software Engineer", 85), *_FILLER], include_round_heading=False
)

# The same (visa_code, occupation_name_raw, round_date) key appears twice
# within a single page — a real possibility in messy government tables —
# reproducing the in-batch duplicate crash (Fix B).
ROUNDS_FIXTURE_WITH_IN_BATCH_DUPLICATE = _rounds_page(
    [("Software Engineer", 85), ("Software Engineer", 85), *_FILLER]
)


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


def test_sync_anzsco_occupations_follows_the_pager(db_session, monkeypatch):
    """The live listing is 12 cards over 103 pages. Without following the
    pager koshi loads 12 of 1,236 occupations."""
    monkeypatch.setattr(pipeline_module, "ANZSCO_PAGE_INTERVAL_SECONDS", 0.0)
    pages = {
        0: _anzsco_page([("261313", "Software Engineer")], last_page=2),
        1: _anzsco_page([("254499", "Registered Nurse")], last_page=2),
        2: _anzsco_page([("2211", "Accountants")], last_page=2),
    }
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        page_no = int(request.url.params.get("page", 0))
        return httpx.Response(200, content=pages[page_no])

    result = sync_anzsco_occupations(
        db_session, client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    assert len(result) == 3
    assert len(requested) == 3  # page 1 registered, pages 2-3 fetched plainly
    assert {o.code for o in result} == {"261313", "254499", "2211"}
    # Only the first page is registered in source_pages - the pages change
    # together, so 103 registry rows would add no signal.
    assert db_session.query(SourcePage).count() == 1
    assert db_session.get(Occupation, "2211").code_grain == "unit_group"
    assert db_session.get(Occupation, "261313").code_grain == "occupation"


def test_sync_anzsco_occupations_is_a_noop_when_page_is_unchanged(db_session):
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))

    result = sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))

    assert result == []  # source_pages saw no content change — nothing re-parsed


def test_sync_skillselect_rounds_persists_on_first_run(db_session):
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))  # occupation FK target

    result = sync_skillselect_rounds(db_session, client=_client_returning(ROUNDS_FIXTURE))

    assert len(result) == 60
    found = db_session.query(EoiRound).filter_by(occupation_name_raw="Software Engineer").one()
    assert found.threshold_points == 85
    assert found.visa_code == "189"  # read from the page, not passed in
    assert found.round_date == dt.date(2026, 7, 24)


def test_sync_skillselect_rounds_leaves_occupation_code_null_without_a_crosswalk(db_session):
    """SkillSelect gives names only. With no crosswalk entry the FK stays
    NULL — the pipeline must not invent a code to fill it."""
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))

    rounds = sync_skillselect_rounds(db_session, client=_client_returning(ROUNDS_FIXTURE))

    assert all(r.occupation_code is None for r in rounds)


def _crosswalk_entry(session, title, code, source="LIN_19_051"):
    session.add(
        OccupationTitle(
            title=title, title_normalized=normalize_title(title),
            occupation_code=code, title_source=source, anzsco_edition="2013",
            source_url="https://www.legislation.gov.au/F2019L00278",
            retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )


def test_sync_skillselect_rounds_resolves_codes_from_the_crosswalk(db_session):
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))
    _crosswalk_entry(db_session, "Software Engineer", "261313")
    db_session.commit()

    rounds = sync_skillselect_rounds(db_session, client=_client_returning(ROUNDS_FIXTURE))

    resolved = [r for r in rounds if r.occupation_code is not None]
    assert len(resolved) == 1
    assert resolved[0].occupation_name_raw == "Software Engineer"
    assert resolved[0].occupation_code == "261313"
    # The filler occupations have no crosswalk entry and stay unresolved,
    # keeping their raw name so they can be resolved later.
    assert all(r.occupation_name_raw for r in rounds if r.occupation_code is None)


def test_crosswalk_does_not_write_a_code_absent_from_occupations(db_session):
    """eoi_rounds.occupation_code is an FK. The crosswalk legitimately holds
    codes koshi's occupations table lacks (LIN 19/051 is ANZSCO 2013; the
    JSA listing is 2022), and writing one would abort the whole batch."""
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))
    _crosswalk_entry(db_session, "Software Engineer", "999999")  # not in occupations
    db_session.commit()

    rounds = sync_skillselect_rounds(db_session, client=_client_returning(ROUNDS_FIXTURE))

    assert all(r.occupation_code is None for r in rounds)


def test_resolved_rounds_produce_momentum_end_to_end(db_session):
    """The point of the crosswalk: momentum was uncomputable while every
    scraped round had a NULL occupation_code."""
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))
    _crosswalk_entry(db_session, "Software Engineer", "261313")
    # Two prior rounds so this sync's round is the third, completing
    # compute_momentum's trailing-3 window.
    for i, points in enumerate([70, 75]):
        db_session.add(
            EoiRound(
                visa_code="189", occupation_code="261313",
                occupation_name_raw="Software Engineer",
                round_date=dt.date(2026, 5, 1) + dt.timedelta(days=30 * i),
                threshold_points=points, invitations_issued=100,
                source_url=SKILLSELECT_ROUNDS_URL,
                retrieved_at=dt.datetime.now(dt.timezone.utc),
                reliability_tier="official_scraped",
            )
        )
    db_session.commit()

    sync_skillselect_rounds(db_session, client=_client_returning(ROUNDS_FIXTURE))

    momentum = db_session.scalar(
        select(OccupationMomentum).where(OccupationMomentum.occupation_code == "261313")
    )
    assert momentum is not None
    assert momentum.direction == "rising"  # 70 -> 75 -> 85


def test_sync_skillselect_rounds_dedups_when_page_hash_changes_but_round_is_identical(db_session):
    sync_anzsco_occupations(db_session, client=_client_returning(ANZSCO_FIXTURE))
    sync_skillselect_rounds(db_session, client=_client_returning(ROUNDS_FIXTURE))

    # Page content changed (new content_hash -> changed=True) but the
    # round itself (visa_code, occupation_name_raw, round_date) is
    # identical. Dedup keys on the *name* precisely because occupation_code
    # is NULL on every row, and Postgres treats NULLs as distinct — a
    # code-keyed check would match nothing and re-insert all 60 rows.
    result = sync_skillselect_rounds(
        db_session, client=_client_returning(ROUNDS_FIXTURE_REPUBLISHED)
    )

    assert result == []  # no new rows were created
    rows = (
        db_session.query(EoiRound)
        .filter_by(occupation_name_raw="Software Engineer", round_date=dt.date(2026, 7, 24))
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
    assert len(result) == 60
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

    # 61 rows in the page (Software Engineer twice + 59 filler) -> 60 persisted.
    assert len(result) == 60  # the in-batch duplicate was skipped, not crashed on
    rows = (
        db_session_no_autoflush.query(EoiRound)
        .filter_by(occupation_name_raw="Software Engineer", round_date=dt.date(2026, 7, 24))
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
                    occupation_name_raw=code,
                    round_date=base_date + dt.timedelta(days=30 * i),
                    threshold_points=points, invitations_issued=100,
                    source_url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
                    retrieved_at=dt.datetime.now(dt.timezone.utc),
                    reliability_tier="official_scraped",
                )
            )
    db_session.commit()

    # A third round each, completing compute_momentum's trailing-3 window.
    for code, points in (("261313", 85), ("254499", 80)):
        db_session.add(
            EoiRound(
                visa_code="189", occupation_code=code, occupation_name_raw=code,
                round_date=dt.date(2026, 7, 24), threshold_points=points,
                invitations_issued=120,
                source_url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
                retrieved_at=dt.datetime.now(dt.timezone.utc),
                reliability_tier="official_scraped",
            )
        )
    db_session.commit()

    original_refresh_momentum = pipeline_module.refresh_momentum

    def flaky_refresh(session, code):
        if code == "261313":
            raise RuntimeError("simulated momentum failure")
        return original_refresh_momentum(session, code)

    monkeypatch.setattr(pipeline_module, "refresh_momentum", flaky_refresh)

    # Driven directly rather than through sync_skillselect_rounds: scraped
    # rounds carry occupation_code = NULL until the crosswalk lands, so the
    # sync currently passes an empty set and this isolation would go
    # untested. The behaviour under test is the loop's, not the sync's.
    pipeline_module.refresh_momentum_for_codes(db_session, {"261313", "254499"})

    working_momentum = db_session.scalar(
        select(OccupationMomentum).where(OccupationMomentum.occupation_code == "254499")
    )
    assert working_momentum is not None
    assert working_momentum.direction == "rising"

    failed_momentum = db_session.scalar(
        select(OccupationMomentum).where(OccupationMomentum.occupation_code == "261313")
    )
    assert failed_momentum is None


def test_momentum_refresh_db_level_failure_does_not_cascade_to_the_next_code(
    db_session_no_autoflush, monkeypatch
):
    # Uses the no-autoflush session (mirrors koshi.db.SessionLocal's real
    # production settings — see the fixture's docstring) because this test
    # is specifically about the real Postgres transaction's abort/recovery
    # behaviour, not just a Python-level exception raised before any DB
    # interaction (that's what test_momentum_refresh_failure_for_one_code_
    # does_not_block_the_other above already covers).
    session = db_session_no_autoflush
    session.add_all([
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
    session.commit()

    # Two prior rounds each, identical trend for both occupations, so the
    # round this test triggers (each occupation's 3rd) completes
    # compute_momentum's trailing-3 window with the same expected
    # direction ("rising") for whichever occupation the loop happens to
    # process second — see the processed_order comment below for why we
    # can't pin down which code that is ahead of time.
    base_date = dt.date(2026, 5, 1)
    for code in ("261313", "254499"):
        for i, points in enumerate([70, 75]):
            session.add(
                EoiRound(
                    visa_code="189", occupation_code=code,
                    occupation_name_raw=code,
                    round_date=base_date + dt.timedelta(days=30 * i),
                    threshold_points=points, invitations_issued=100,
                    source_url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
                    retrieved_at=dt.datetime.now(dt.timezone.utc),
                    reliability_tier="official_scraped",
                )
            )
    session.commit()

    # A third round each, completing compute_momentum's trailing-3 window.
    for code in ("261313", "254499"):
        session.add(
            EoiRound(
                visa_code="189", occupation_code=code, occupation_name_raw=code,
                round_date=dt.date(2026, 7, 24), threshold_points=85,
                invitations_issued=120,
                source_url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
                retrieved_at=dt.datetime.now(dt.timezone.utc),
                reliability_tier="official_scraped",
            )
        )
    session.commit()

    original_refresh_momentum = pipeline_module.refresh_momentum
    # refresh_momentum_for_codes iterates a Python set, so we can't know
    # ahead of time which of the two codes the loop visits first — record
    # the actual order live instead of hard-coding one.
    processed_order: list[str] = []

    def flaky_refresh(session, code):
        processed_order.append(code)
        if len(processed_order) == 1:
            # Genuinely poison the session's real Postgres transaction —
            # not a pre-DB Python exception — the same way a constraint
            # violation, stale row, or connection hiccup would in
            # production: a raw statement Postgres itself rejects.
            session.execute(text("SELECT 1/0"))
        else:
            original_refresh_momentum(session, code)

    monkeypatch.setattr(pipeline_module, "refresh_momentum", flaky_refresh)

    # Driven directly rather than through sync_skillselect_rounds — see the
    # sibling test above for why.
    pipeline_module.refresh_momentum_for_codes(session, {"261313", "254499"})

    assert len(processed_order) == 2  # the loop attempted both codes, not just the first
    poisoned_code, recovered_code = processed_order

    poisoned_momentum = session.scalar(
        select(OccupationMomentum).where(OccupationMomentum.occupation_code == poisoned_code)
    )
    assert poisoned_momentum is None

    # The point of this test: the code processed AFTER the DB-level
    # failure must still get its momentum computed correctly. Without
    # session.rollback() in the except block, this call would itself
    # raise against the still-aborted transaction, get caught by the same
    # except, and this occupation would be spuriously reported as failed
    # too — even though its own data was perfectly fine.
    recovered_momentum = session.scalar(
        select(OccupationMomentum).where(OccupationMomentum.occupation_code == recovered_code)
    )
    assert recovered_momentum is not None
    assert recovered_momentum.direction == "rising"
