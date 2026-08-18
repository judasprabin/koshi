import koshi.__main__ as main_module


class _FakeSession:
    """Stands in for SessionLocal() in these tests — the sync/seed
    functions are monkeypatched below and never touch it, so a real DB
    connection isn't needed to test main()'s control flow."""

    def execute(self, *args, **kwargs):
        # Stands in for the post-construction liveness check
        # (session.execute(text("SELECT 1"))) — a no-op success here, so
        # these tests exercise control flow past init exactly as before.
        return None

    def rollback(self):
        pass

    def close(self):
        pass


def test_main_returns_0_when_all_steps_succeed(monkeypatch):
    monkeypatch.setattr(main_module, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(main_module, "sync_anzsco_occupations", lambda session: [1, 2])
    monkeypatch.setattr(main_module, "sync_abs_occupations", lambda session: [1])
    monkeypatch.setattr(main_module, "sync_occupation_titles", lambda session: [1])
    monkeypatch.setattr(main_module, "sync_skillselect_rounds", lambda session: [1])
    monkeypatch.setattr(main_module, "seed_ceiling_usage", lambda session, path: [1, 2, 3])

    exit_code = main_module.main()

    assert exit_code == 0


def test_main_returns_2_and_still_runs_remaining_steps_when_one_step_fails(monkeypatch):
    calls = []

    def failing_sync(session):
        calls.append("anzsco")
        raise RuntimeError("boom")

    def ok_abs(session):
        calls.append("abs")
        return [1]

    def ok_titles(session):
        calls.append("titles")
        return [1]

    def ok_sync(session):
        calls.append("skillselect")
        return [1]

    def ok_seed(session, path):
        calls.append("ceiling")
        return [1]

    monkeypatch.setattr(main_module, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(main_module, "sync_anzsco_occupations", failing_sync)
    monkeypatch.setattr(main_module, "sync_abs_occupations", ok_abs)
    monkeypatch.setattr(main_module, "sync_occupation_titles", ok_titles)
    monkeypatch.setattr(main_module, "sync_skillselect_rounds", ok_sync)
    monkeypatch.setattr(main_module, "seed_ceiling_usage", ok_seed)

    exit_code = main_module.main()

    assert exit_code == 2
    assert calls == ["anzsco", "abs", "titles", "skillselect", "ceiling"]


def test_main_returns_3_when_all_steps_fail(monkeypatch):
    def failing(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(main_module, "sync_anzsco_occupations", failing)
    # Every step must be patched: an unpatched one calls the real sync,
    # which would reach the network from a unit test and make this pass for
    # the wrong reason (it fails anyway, so exit 3 still holds).
    monkeypatch.setattr(main_module, "sync_abs_occupations", failing)
    monkeypatch.setattr(main_module, "sync_occupation_titles", failing)
    monkeypatch.setattr(main_module, "sync_skillselect_rounds", failing)
    monkeypatch.setattr(main_module, "seed_ceiling_usage", failing)

    exit_code = main_module.main()

    assert exit_code == 3


def test_main_returns_1_when_session_initialization_fails(monkeypatch):
    def failing_session_local():
        raise RuntimeError("cannot connect")

    monkeypatch.setattr(main_module, "SessionLocal", failing_session_local)

    exit_code = main_module.main()

    assert exit_code == 1


def test_main_returns_1_when_database_is_unreachable(monkeypatch):
    """Proves the liveness check is what actually catches an unreachable
    database — SessionLocal() itself succeeds (matching real SQLAlchemy
    behaviour: sessionmaker() only constructs a Session, it doesn't open a
    connection), and the failure only surfaces on the first real query.
    Without the liveness check in main(), this scenario would instead slip
    past the init except block and fail inside step 1, yielding exit code
    3 rather than 1 — this is the real-world case
    test_main_returns_1_when_session_initialization_fails doesn't cover.
    """

    class _UnreachableDbSession:
        def execute(self, *args, **kwargs):
            raise RuntimeError("could not connect to server: Connection refused")

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(main_module, "SessionLocal", lambda: _UnreachableDbSession())

    exit_code = main_module.main()

    assert exit_code == 1


def test_main_writes_a_run_summary_reflecting_each_steps_outcome(monkeypatch):
    written = {}

    def fake_write_run_summary(summary):
        written["summary"] = summary
        return "fake-path"

    monkeypatch.setattr(main_module, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(main_module, "sync_anzsco_occupations", lambda session: [1])
    monkeypatch.setattr(main_module, "sync_abs_occupations", lambda session: [])
    monkeypatch.setattr(main_module, "sync_occupation_titles", lambda session: [])
    monkeypatch.setattr(main_module, "sync_skillselect_rounds", lambda session: [])
    monkeypatch.setattr(main_module, "seed_ceiling_usage", lambda session, path: [])
    monkeypatch.setattr(main_module, "write_run_summary", fake_write_run_summary)

    exit_code = main_module.main()

    assert "summary" in written
    summary = written["summary"]
    assert summary["steps"][0] == {"name": "anzsco_occupations", "status": "ok", "count": 1}
    assert summary["steps"][1] == {"name": "abs_occupations", "status": "ok", "count": 0}
    assert summary["steps"][2] == {"name": "occupation_titles", "status": "ok", "count": 0}
    assert summary["steps"][3] == {"name": "skillselect_rounds", "status": "ok", "count": 0}
    assert summary["steps"][4] == {"name": "ceiling_usage_seed", "status": "ok", "count": 0}
    # finished_at/exit_code must land in the written summary, not just be
    # returned from main() — a summary file read after the fact is the
    # only observability a cron-triggered run has.
    assert "finished_at" in summary
    assert summary["finished_at"] >= summary["started_at"]
    assert summary["exit_code"] == 0 == exit_code


def test_main_writes_an_error_detail_for_a_failed_step(monkeypatch):
    written = {}

    def fake_write_run_summary(summary):
        written["summary"] = summary
        return "fake-path"

    def failing_sync(session):
        raise RuntimeError("boom: upstream table not found")

    monkeypatch.setattr(main_module, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(main_module, "sync_anzsco_occupations", failing_sync)
    # Patched so this unit test never reaches the network.
    monkeypatch.setattr(main_module, "sync_abs_occupations", lambda session: [])
    monkeypatch.setattr(main_module, "sync_occupation_titles", lambda session: [])
    monkeypatch.setattr(main_module, "sync_skillselect_rounds", lambda session: [])
    monkeypatch.setattr(main_module, "seed_ceiling_usage", lambda session, path: [])
    monkeypatch.setattr(main_module, "write_run_summary", fake_write_run_summary)

    exit_code = main_module.main()

    failed_step = written["summary"]["steps"][0]
    assert failed_step["name"] == "anzsco_occupations"
    assert failed_step["status"] == "failed"
    assert failed_step["error"] == "RuntimeError: boom: upstream table not found"
    assert written["summary"]["exit_code"] == 2 == exit_code


class _RowsWithSkipped(list):
    """Minimal stand-in for pipeline._RowsWithSkipCount — a plain list
    with a bonus `.skipped` attribute, exactly the shape
    sync_anzsco_occupations/sync_skillselect_rounds return in production
    so this test doesn't need a real DB/parser round-trip to prove
    __main__.py reads the attribute correctly."""

    skipped: int = 0


def test_main_threads_parser_skip_count_into_the_step_summary(monkeypatch):
    written = {}

    def fake_write_run_summary(summary):
        written["summary"] = summary
        return "fake-path"

    anzsco_result = _RowsWithSkipped([1, 2])
    anzsco_result.skipped = 4
    skillselect_result = _RowsWithSkipped([1])
    skillselect_result.skipped = 0

    monkeypatch.setattr(main_module, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(main_module, "sync_anzsco_occupations", lambda session: anzsco_result)
    monkeypatch.setattr(main_module, "sync_abs_occupations", lambda session: [])
    monkeypatch.setattr(main_module, "sync_occupation_titles", lambda session: [])
    monkeypatch.setattr(main_module, "sync_skillselect_rounds", lambda session: skillselect_result)
    # ceiling_usage_seed returns a plain list in production (no parser skip
    # count to surface) — must not gain a "skipped" key from unrelated code.
    monkeypatch.setattr(main_module, "seed_ceiling_usage", lambda session, path: [1])
    monkeypatch.setattr(main_module, "write_run_summary", fake_write_run_summary)

    main_module.main()

    steps = written["summary"]["steps"]
    assert steps[0]["skipped"] == 4
    assert steps[3]["skipped"] == 0
    assert "skipped" not in steps[4]
