# koshi ETL Phase 0 — Fault-Tolerance Retrofit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retrofit koshi's 2 existing sources (ANZSCO occupations, SkillSelect EOI rounds) with real fault tolerance — retry/backoff, per-row/per-entry isolation, structured logging, run summaries, and meaningful exit codes — before any new source is added.

**Architecture:** No new tables, no new sources, no new API surface. Every change lands inside the existing ingestion pipeline (`crawler/fetch.py`, both `extraction/*.py` parsers, `seeds/loader.py`, `pipeline.py`, `__main__.py`), replacing today's zero-exception-handling, zero-logging pipeline with one that survives a bad row, a network blip, or a partial failure without crashing the whole run or corrupting data.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0, `tenacity` (new dependency), pytest, real Postgres in tests (no mocked DB), `httpx.MockTransport` for network tests.

## Global Constraints

- Retry only transient failures — `httpx.TransportError`, or an HTTP status in `(429, 500, 502, 503, 504)`. Never retry a 404/400 or a parse error — those fail identically on retry; the extraction watermark already handles retry-on-next-run for parse failures.
- Per-row (parsers) and per-entry (seed loader) failures are soft-fails: skip, log a warning, continue. Never let one bad row/entry abort an otherwise-good batch or file.
- `__main__.py` exit codes: `0` clean, `1` fatal init failure (session construction itself fails, before any step runs), `2` partial failure (some steps ok, some failed), `3` total failure (every step failed). All four are real, reachable, tested code paths — not aspirational.
- New dependency: `tenacity>=8.2.0`.
- Structured logging replaces every bare `print()` — dual stdout + `RotatingFileHandler` (5MB, 3 backups) to `logs/koshi.log`, `logs/` gitignored.
- No new data source, no source-registry pattern, no scheduling/deployment work — those are separate, later plans (see `docs/superpowers/specs/2026-08-15-koshi-etl-finalization-design.md` §9, Phases 1+).
- Existing public function signatures (`sync_anzsco_occupations`, `sync_skillselect_rounds`, `seed_ceiling_usage`, `load_ceiling_usage_seed`) do not change — only their internals and (for the two parser functions, explicitly) their return type.
- Current baseline before this plan: 51 tests passing (`.venv/bin/pytest -q`). Every task must leave the full suite green.

---

### Task 1: `logging_config.py` — structured logging setup

**Files:**
- Create: `src/koshi/logging_config.py`
- Test: `tests/test_logging_config.py`

**Interfaces:**
- Produces: `koshi.logging_config.setup_logging(*, level: int = logging.INFO) -> None`, `koshi.logging_config.LOG_FILE` (a `pathlib.Path`) — Task 9 (`__main__.py`) calls `setup_logging()` once at process start.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_logging_config.py
import logging

from koshi.logging_config import LOG_FILE, setup_logging


def test_setup_logging_creates_log_file_and_writes_to_it():
    setup_logging()
    logger = logging.getLogger("test_koshi_logging_config")
    logger.info("hello from test_setup_logging_creates_log_file_and_writes_to_it")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert LOG_FILE.exists()
    assert "hello from test_setup_logging_creates_log_file_and_writes_to_it" in LOG_FILE.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_logging_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'koshi.logging_config'`

- [ ] **Step 3: Write the implementation**

```python
# src/koshi/logging_config.py
"""Structured logging setup for koshi's ETL pipeline.

Ports the dual stdout + rotating-file pattern already proven in
research/au-visa-sources/main.py — koshi's own crawler was rebuilt from
that repo, but its logging discipline never came with it. Every module
gets `logger = logging.getLogger(__name__)`; this module only wires up
where those log records go.
"""
import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "koshi.log"


def setup_logging(*, level: int = logging.INFO) -> None:
    """Configure the root logger with a stdout handler and a rotating
    file handler (5MB per file, 3 backups kept). Call once, at process
    start — koshi.__main__.main() is the only caller in this codebase.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_logging_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/koshi/logging_config.py tests/test_logging_config.py
git commit -m "Add structured logging setup, ported from research/au-visa-sources"
```

---

### Task 2: `resilience.py` — per-item isolation, loose int parsing, throttling

**Files:**
- Create: `src/koshi/resilience.py`
- Test: `tests/test_resilience.py`

**Interfaces:**
- Produces: `koshi.resilience.parse_int_loose(text: str) -> int | None` — Task 6 (SkillSelect parser) uses this for numeric fields.
- Produces: `koshi.resilience.isolated_item(session: Session, description: str)` — a context manager — Task 8 (seed loader) uses this to scope one seed entry's persistence inside a SAVEPOINT.
- Produces: `koshi.resilience.Throttler` — a class with `__init__(self, min_interval_seconds: float)` and `wait(self) -> None`. Not wired into any call site in this plan (Global Constraints: no source-registry work here) — built and tested standalone, ready for Phase 1.

- [ ] **Step 1: Write the failing tests — `parse_int_loose`**

```python
# tests/test_resilience.py
import time

import pytest

from koshi.resilience import Throttler, isolated_item, parse_int_loose


def test_parse_int_loose_parses_plain_digit_string():
    assert parse_int_loose("120") == 120


def test_parse_int_loose_strips_thousands_separator():
    assert parse_int_loose("1,234") == 1234


def test_parse_int_loose_maps_placeholder_tokens_to_none():
    assert parse_int_loose("N/A") is None
    assert parse_int_loose("-") is None
    assert parse_int_loose("") is None


def test_parse_int_loose_raises_on_garbage():
    with pytest.raises(ValueError):
        parse_int_loose("not a number")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_resilience.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'koshi.resilience'`

- [ ] **Step 3: Write `parse_int_loose`**

```python
# src/koshi/resilience.py
"""Cross-cutting fault-tolerance helpers used by koshi's ETL pipeline."""
import contextlib
import logging
import time

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_PLACEHOLDER_TOKENS = {"", "-", "N/A", "n/a"}


def parse_int_loose(text: str) -> int | None:
    """Parse an int from real-world government-table formatting.

    Strips thousands separators ("1,234" -> 1234) and maps common
    placeholder tokens ("N/A", "-", "") to None. Raises ValueError on
    genuine garbage — a caller that can't tolerate that should catch it,
    not this function.
    """
    cleaned = text.strip().replace(",", "")
    if cleaned in _PLACEHOLDER_TOKENS:
        return None
    return int(cleaned)
```

- [ ] **Step 4: Run `parse_int_loose` tests to verify they pass**

Run: `.venv/bin/pytest tests/test_resilience.py -v -k parse_int_loose`
Expected: PASS (4 tests)

- [ ] **Step 5: Write the failing tests — `isolated_item`**

```python
# tests/test_resilience.py (add)
import datetime as dt

from koshi.models.occupations import Occupation


def test_isolated_item_lets_the_session_continue_after_a_failure(db_session):
    with isolated_item(db_session, "bad row"):
        raise ValueError("boom")

    db_session.add(
        Occupation(
            code="999991", name="Still Works", unit_group="test",
            source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()

    found = db_session.get(Occupation, "999991")
    assert found is not None


def test_isolated_item_persists_successful_work(db_session):
    with isolated_item(db_session, "good row"):
        db_session.add(
            Occupation(
                code="999992", name="Good Row", unit_group="test",
                source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
                reliability_tier="official_scraped",
            )
        )
    db_session.commit()

    found = db_session.get(Occupation, "999992")
    assert found is not None
```

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_resilience.py -v -k isolated_item`
Expected: FAIL — `ImportError: cannot import name 'isolated_item'`

- [ ] **Step 7: Write `isolated_item`**

```python
# src/koshi/resilience.py (add)
@contextlib.contextmanager
def isolated_item(session: Session, description: str):
    """Scope one item's DB work inside a SAVEPOINT, so a failure in it
    doesn't poison the enclosing transaction.

    Postgres aborts the whole transaction on a failed statement unless a
    savepoint scopes the failure — a bare try/except around
    session.add()/session.commit() alone does NOT provide this; the next
    statement on a poisoned transaction still fails.
    """
    nested = session.begin_nested()
    try:
        yield
        nested.commit()
    except Exception:
        nested.rollback()
        logger.exception("skipped %s due to an error", description)
```

- [ ] **Step 8: Run `isolated_item` tests to verify they pass**

Run: `.venv/bin/pytest tests/test_resilience.py -v -k isolated_item`
Expected: PASS (2 tests)

- [ ] **Step 9: Write the failing test — `Throttler`**

```python
# tests/test_resilience.py (add)
def test_throttler_waits_at_least_min_interval_between_calls():
    throttler = Throttler(min_interval_seconds=0.05)
    throttler.wait()
    start = time.monotonic()
    throttler.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.05
```

- [ ] **Step 10: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_resilience.py -v -k Throttler`
Expected: FAIL — `ImportError: cannot import name 'Throttler'`

- [ ] **Step 11: Write `Throttler`**

```python
# src/koshi/resilience.py (add)
class Throttler:
    """Minimum-interval rate limiter, ported from the pattern in
    research/au-visa-sources/crawler.py's _throttle(). Not wired into any
    call site yet — matters once a single run fetches multiple URLs,
    which isn't true yet (see the ETL finalization design doc §8)."""

    def __init__(self, min_interval_seconds: float):
        self.min_interval_seconds = min_interval_seconds
        self._last_call: float | None = None

    def wait(self) -> None:
        if self._last_call is not None:
            elapsed = time.monotonic() - self._last_call
            remaining = self.min_interval_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_call = time.monotonic()
```

- [ ] **Step 12: Run the full test file to verify everything passes**

Run: `.venv/bin/pytest tests/test_resilience.py -v`
Expected: PASS (7 tests)

- [ ] **Step 13: Commit**

```bash
git add src/koshi/resilience.py tests/test_resilience.py
git commit -m "Add resilience.py: parse_int_loose, isolated_item, Throttler"
```

---

### Task 3: `run_summary.py` — JSON run summary per invocation

**Files:**
- Create: `src/koshi/run_summary.py`
- Test: `tests/test_run_summary.py`

**Interfaces:**
- Produces: `koshi.run_summary.write_run_summary(summary: dict) -> Path` — Task 9 (`__main__.py`) calls this once at the end of `main()`. `summary` must include a `"started_at"` key (an ISO-8601 string, e.g. from `dt.datetime.now(dt.timezone.utc).isoformat()`).
- Produces: `koshi.run_summary.SUMMARY_DIR` (a `pathlib.Path`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_summary.py
import json

from koshi.run_summary import SUMMARY_DIR, write_run_summary


def test_write_run_summary_writes_json_file_and_returns_path():
    summary = {
        "started_at": "2026-08-15T10:00:00+00:00",
        "steps": [{"name": "anzsco_occupations", "status": "ok", "count": 5}],
    }

    path = write_run_summary(summary)

    assert path.exists()
    assert path.parent == SUMMARY_DIR
    written = json.loads(path.read_text())
    assert written == summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_run_summary.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'koshi.run_summary'`

- [ ] **Step 3: Write the implementation**

```python
# src/koshi/run_summary.py
"""JSON run-summary writer for koshi's ETL pipeline, ported from the
pattern in research/au-visa-sources/main.py's _write_summary(). Every
`python -m koshi` invocation writes one summary file — the pipeline has
no other observability beyond log lines."""
import json
from pathlib import Path

SUMMARY_DIR = Path(__file__).resolve().parent.parent.parent / "logs" / "summaries"


def write_run_summary(summary: dict) -> Path:
    """Write summary as JSON to logs/summaries/run_<started_at>.json and
    return the path written."""
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    safe_timestamp = summary["started_at"].replace(":", "-")
    path = SUMMARY_DIR / f"run_{safe_timestamp}.json"
    path.write_text(json.dumps(summary, indent=2))
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_run_summary.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/koshi/run_summary.py tests/test_run_summary.py
git commit -m "Add JSON run-summary writer, ported from research/au-visa-sources"
```

---

### Task 4: `crawler/fetch.py` — split timeout, retry/backoff, typed `FetchError`

**Files:**
- Modify: `pyproject.toml` (add `tenacity>=8.2.0` to `dependencies`)
- Modify: `src/koshi/crawler/fetch.py`
- Modify: `tests/test_crawler_fetch.py`

**Interfaces:**
- Consumes: nothing new from earlier tasks in this plan.
- Produces: `koshi.crawler.fetch.FetchError` (exception, attributes `url`/`domain`/`category`/`cause`) — no other task in this plan catches it directly, but it's the exception `__main__.py`'s per-step `except Exception` (Task 9) will see bubble up from a sync function when a fetch is exhausted. `fetch_and_register`'s signature and return type (`tuple[SourcePage, bool, str]`) are unchanged.

- [ ] **Step 1: Add the dependency**

```toml
# pyproject.toml — add to the existing dependencies list, alongside "httpx>=0.27"
    "tenacity>=8.2.0",
```

Run: `.venv/bin/pip install -e ".[dev]"`

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_crawler_fetch.py (add)
import httpx
import pytest

from koshi.crawler.fetch import FetchError, fetch_and_register


def test_fetch_and_register_retries_transient_failures_then_succeeds(db_session, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)  # keep the test fast
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503, content=b"unavailable")
        return httpx.Response(200, content=b"<html>ok</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    page, changed, text = fetch_and_register(
        db_session,
        url="https://immi.homeaffairs.gov.au/retry-test",
        domain="immi.homeaffairs.gov.au",
        category="test",
        client=client,
    )

    assert attempts["count"] == 3
    assert changed is True
    assert text == "<html>ok</html>"


def test_fetch_and_register_raises_fetch_error_after_exhausting_retries(db_session, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"unavailable")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(FetchError):
        fetch_and_register(
            db_session,
            url="https://immi.homeaffairs.gov.au/always-503",
            domain="immi.homeaffairs.gov.au",
            category="test",
            client=client,
        )


def test_fetch_and_register_does_not_retry_a_404(db_session):
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404, content=b"not found")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(FetchError):
        fetch_and_register(
            db_session,
            url="https://immi.homeaffairs.gov.au/missing",
            domain="immi.homeaffairs.gov.au",
            category="test",
            client=client,
        )

    assert attempts["count"] == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_crawler_fetch.py -v -k "retries or FetchError or does_not_retry"`
Expected: FAIL — `ImportError: cannot import name 'FetchError'`

- [ ] **Step 4: Rewrite `fetch.py`**

```python
# src/koshi/crawler/fetch.py
import datetime as dt
import hashlib
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from koshi.models.source_pages import SourcePage

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """Raised when a page could not be fetched after exhausting retries."""

    def __init__(self, *, url: str, domain: str, category: str, cause: Exception):
        self.url = url
        self.domain = domain
        self.category = category
        self.cause = cause
        super().__init__(f"failed to fetch {url!r} ({domain}/{category}): {cause!r}")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return False


def hash_content(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    before_sleep=lambda retry_state: logger.warning(
        "retrying fetch (attempt %d) after %r",
        retry_state.attempt_number,
        retry_state.outcome.exception(),
    ),
    reraise=True,
)
def _get_with_retry(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def fetch_and_register(
    session: Session,
    *,
    url: str,
    domain: str,
    category: str,
    client: httpx.Client | None = None,
) -> tuple[SourcePage, bool, str]:
    """Fetch a page, hash it, and upsert into source_pages.

    Returns (page, changed, text). changed is True for a brand-new page or
    one whose content_hash differs from what's stored. text is the response
    body decoded per httpx's own encoding detection (response.text) —
    callers that need to parse the page reuse it instead of fetching a
    second time.

    Retries transient failures (network errors, 429/5xx) with exponential
    backoff; raises FetchError once retries are exhausted or on a
    non-retryable status (e.g. 404) — never retries those, since they'll
    fail identically next time.

    NOTE: content_hash/last_changed_at are committed here, before the
    caller has attempted to parse `text`. A caller must NOT treat `changed`
    (or content_hash) as proof that it has successfully parsed and
    persisted this page's content — see SourcePage.last_extracted_at and
    pipeline.py's _needs_extraction for the watermark that actually tracks
    that.
    """
    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=10.0)
    )
    try:
        try:
            response = _get_with_retry(active_client, url)
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            raise FetchError(url=url, domain=domain, category=category, cause=exc) from exc
        content = response.content
        text = response.text
        content_hash = hash_content(content)
    finally:
        if owns_client:
            active_client.close()

    now = dt.datetime.now(dt.timezone.utc)
    existing = session.scalar(select(SourcePage).where(SourcePage.url == url))

    if existing is None:
        page = SourcePage(
            url=url,
            domain=domain,
            category=category,
            content_hash=content_hash,
            first_seen_at=now,
            last_checked_at=now,
            last_changed_at=now,
            status="active",
        )
        session.add(page)
        session.commit()
        return page, True, text

    changed = existing.content_hash != content_hash
    existing.last_checked_at = now
    if changed:
        existing.content_hash = content_hash
        existing.last_changed_at = now
    session.commit()
    return existing, changed, text
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `.venv/bin/pytest tests/test_crawler_fetch.py -v`
Expected: PASS (all tests, including the 3 pre-existing ones from Task 3 of the occupation-slice plan)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/koshi/crawler/fetch.py tests/test_crawler_fetch.py
git commit -m "Add retry/backoff, split timeout, and typed FetchError to crawler/fetch.py"
```

---

### Task 5: `extraction/anzsco_occupations.py` — `ParseResult` + per-row isolation

**Files:**
- Modify: `src/koshi/extraction/anzsco_occupations.py`
- Modify: `tests/test_extraction_anzsco.py`
- Create: `tests/fixtures/anzsco_sample_malformed.html`

**Interfaces:**
- Produces: `koshi.extraction.anzsco_occupations.ParseResult` (dataclass: `rows: list[Occupation]`, `skipped: int`).
- Produces: `parse_anzsco_occupations(html, *, source_url, retrieved_at) -> ParseResult` — **return type changed** from a bare `list[Occupation]`. Task 7 (`pipeline.py`) is updated to consume `.rows` from this.

- [ ] **Step 1: Write the malformed-row fixture and the failing test**

```html
<!-- tests/fixtures/anzsco_sample_malformed.html -->
<table id="occupation-list">
  <thead><tr><th>ANZSCO Code</th><th>Occupation</th><th>Unit Group</th></tr></thead>
  <tbody>
    <tr><td>261313</td><td>Software Engineer</td><td>2613 Software and Applications Programmers</td></tr>
    <tr><td>Malformed Row</td><td>only two cells</td></tr>
    <tr><td>254499</td><td>Registered Nurse (Aged Care)</td><td>2544 Registered Nurses</td></tr>
  </tbody>
</table>
```

```python
# tests/test_extraction_anzsco.py — add
from pathlib import Path

from koshi.extraction.anzsco_occupations import parse_anzsco_occupations

MALFORMED_FIXTURE = (Path(__file__).parent / "fixtures" / "anzsco_sample_malformed.html").read_text()


def test_parses_good_rows_and_skips_a_malformed_row():
    result = parse_anzsco_occupations(
        MALFORMED_FIXTURE, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT
    )
    assert len(result.rows) == 2
    assert result.skipped == 1
    codes = {o.code for o in result.rows}
    assert codes == {"261313", "254499"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_extraction_anzsco.py -v -k malformed`
Expected: FAIL — `AttributeError` (the parser doesn't skip yet, it would raise `ValueError: too many values to unpack` on the malformed row today)

- [ ] **Step 3: Update the existing tests for the `ParseResult` return type**

```python
# tests/test_extraction_anzsco.py — modify the two existing tests
def test_parses_two_occupations_from_fixture():
    result = parse_anzsco_occupations(FIXTURE, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT)

    assert len(result.rows) == 2
    assert result.skipped == 0
    swe = next(o for o in result.rows if o.code == "261313")
    assert swe.name == "Software Engineer"
    assert swe.unit_group == "2613 Software and Applications Programmers"
    assert swe.reliability_tier == "official_scraped"
    assert swe.source_url == SOURCE_URL
    assert swe.retrieved_at == RETRIEVED_AT


def test_persists_parsed_occupations(db_session):
    result = parse_anzsco_occupations(FIXTURE, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT)
    db_session.add_all(result.rows)
    db_session.commit()

    from koshi.models.occupations import Occupation

    found = db_session.get(Occupation, "254499")
    assert found.name == "Registered Nurse (Aged Care)"
```

- [ ] **Step 4: Rewrite the parser**

```python
# src/koshi/extraction/anzsco_occupations.py
import dataclasses
import datetime as dt
import logging

from bs4 import BeautifulSoup

from koshi.models.occupations import Occupation
from koshi.provenance import require_provenance

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ParseResult:
    rows: list[Occupation]
    skipped: int


def parse_anzsco_occupations(
    html: str, *, source_url: str, retrieved_at: dt.datetime
) -> ParseResult:
    require_provenance(
        reliability_tier="official_scraped", source_url=source_url, retrieved_at=retrieved_at
    )

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="occupation-list")
    if table is None:
        raise ValueError("occupation-list table not found — possible page redesign")
    tbody = table.find("tbody")
    if tbody is None:
        raise ValueError("occupation-list table has no tbody — possible page redesign")
    rows = tbody.find_all("tr")

    occupations: list[Occupation] = []
    skipped = 0
    for index, row in enumerate(rows):
        cells = row.find_all("td")
        try:
            code, name, unit_group = (c.get_text(strip=True) for c in cells)
        except ValueError as exc:
            logger.warning(
                "skipping ANZSCO row %d: %r (cell texts=%r)",
                index, exc, [c.get_text(strip=True) for c in cells],
            )
            skipped += 1
            continue

        occupations.append(
            Occupation(
                code=code,
                name=name,
                unit_group=unit_group,
                source_url=source_url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
    return ParseResult(rows=occupations, skipped=skipped)
```

- [ ] **Step 5: Run all tests in the file to verify they pass**

Run: `.venv/bin/pytest tests/test_extraction_anzsco.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add src/koshi/extraction/anzsco_occupations.py tests/test_extraction_anzsco.py tests/fixtures/anzsco_sample_malformed.html
git commit -m "Add per-row isolation to the ANZSCO parser (ParseResult, skip-and-continue)"
```

---

### Task 6: `extraction/skillselect_rounds.py` — `ParseResult` + per-row isolation + loose int parsing

**Files:**
- Modify: `src/koshi/extraction/skillselect_rounds.py`
- Modify: `tests/test_extraction_skillselect.py`
- Create: `tests/fixtures/skillselect_rounds_sample_malformed.html`

**Interfaces:**
- Consumes: `koshi.resilience.parse_int_loose` (Task 2).
- Produces: `koshi.extraction.skillselect_rounds.ParseResult` (dataclass: `rows: list[EoiRound]`, `skipped: int`).
- Produces: `parse_skillselect_rounds(html, *, visa_code, source_url, retrieved_at) -> ParseResult` — **return type changed**. Task 7 updates `pipeline.py` to consume `.rows`.

- [ ] **Step 1: Write the malformed/real-world-formatting fixture and the failing test**

```html
<!-- tests/fixtures/skillselect_rounds_sample_malformed.html -->
<p>Round date: 24 July 2026</p>
<table id="round-results">
  <thead><tr><th>Occupation</th><th>Points Threshold</th><th>Invitations Issued</th></tr></thead>
  <tbody>
    <tr><td>261313</td><td>85</td><td>1,234</td></tr>
    <tr><td>254499</td><td>75</td><td>N/A</td></tr>
    <tr><td>Malformed Row</td><td>only two cells</td></tr>
  </tbody>
</table>
```

```python
# tests/test_extraction_skillselect.py — add
from pathlib import Path

from koshi.extraction.skillselect_rounds import parse_skillselect_rounds

MALFORMED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "skillselect_rounds_sample_malformed.html"
).read_text()


def test_parses_thousands_separator_and_na_placeholder_skips_malformed_row():
    result = parse_skillselect_rounds(
        MALFORMED_FIXTURE, visa_code="189", source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT
    )
    assert len(result.rows) == 2
    assert result.skipped == 1

    swe = next(r for r in result.rows if r.occupation_code == "261313")
    assert swe.invitations_issued == 1234

    nurse = next(r for r in result.rows if r.occupation_code == "254499")
    assert nurse.invitations_issued is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_extraction_skillselect.py -v -k thousands_separator`
Expected: FAIL — `ValueError: invalid literal for int() with base 10: '1,234'` (today's `int()` call can't handle this)

- [ ] **Step 3: Update the existing tests for the `ParseResult` return type**

```python
# tests/test_extraction_skillselect.py — modify the two existing tests
def test_parses_round_date_and_two_rows():
    result = parse_skillselect_rounds(
        FIXTURE, visa_code="189", source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT
    )

    assert len(result.rows) == 2
    assert result.skipped == 0
    swe = next(r for r in result.rows if r.occupation_code == "261313")
    assert swe.round_date == dt.date(2026, 7, 24)
    assert swe.threshold_points == 85
    assert swe.invitations_issued == 120
    assert swe.visa_code == "189"
    assert swe.reliability_tier == "official_scraped"


def test_raises_if_round_date_missing():
    import pytest

    bad_html = "<table id='round-results'><tbody></tbody></table>"
    with pytest.raises(ValueError, match="round date"):
        parse_skillselect_rounds(
            bad_html, visa_code="189", source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT
        )
```

- [ ] **Step 4: Rewrite the parser**

```python
# src/koshi/extraction/skillselect_rounds.py
import dataclasses
import datetime as dt
import logging
import re

from bs4 import BeautifulSoup

from koshi.models.eoi_rounds import EoiRound
from koshi.provenance import require_provenance
from koshi.resilience import parse_int_loose

logger = logging.getLogger(__name__)

ROUND_DATE_RE = re.compile(r"Round date:\s*(\d{1,2} \w+ \d{4})")


@dataclasses.dataclass
class ParseResult:
    rows: list[EoiRound]
    skipped: int


def parse_skillselect_rounds(
    html: str, *, visa_code: str, source_url: str, retrieved_at: dt.datetime
) -> ParseResult:
    require_provenance(
        reliability_tier="official_scraped", source_url=source_url, retrieved_at=retrieved_at
    )

    soup = BeautifulSoup(html, "lxml")
    date_match = ROUND_DATE_RE.search(soup.get_text())
    if not date_match:
        raise ValueError("could not find round date in page")
    round_date = dt.datetime.strptime(date_match.group(1), "%d %B %Y").date()

    table = soup.find("table", id="round-results")
    if table is None:
        raise ValueError("round-results table not found — possible page redesign")
    tbody = table.find("tbody")
    if tbody is None:
        raise ValueError("round-results table has no tbody — possible page redesign")
    rows = tbody.find_all("tr")

    results: list[EoiRound] = []
    skipped = 0
    for index, row in enumerate(rows):
        cells = row.find_all("td")
        try:
            occupation_code, threshold_text, invitations_text = (
                c.get_text(strip=True) for c in cells
            )
            threshold_points = parse_int_loose(threshold_text)
            if threshold_points is None:
                raise ValueError(f"threshold_points is required, got {threshold_text!r}")
            invitations_issued = parse_int_loose(invitations_text)
        except ValueError as exc:
            logger.warning(
                "skipping SkillSelect row %d: %r (cell texts=%r)",
                index, exc, [c.get_text(strip=True) for c in cells],
            )
            skipped += 1
            continue

        results.append(
            EoiRound(
                visa_code=visa_code,
                occupation_code=occupation_code,
                round_date=round_date,
                threshold_points=threshold_points,
                invitations_issued=invitations_issued,
                source_url=source_url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
    return ParseResult(rows=results, skipped=skipped)
```

- [ ] **Step 5: Run all tests in the file to verify they pass**

Run: `.venv/bin/pytest tests/test_extraction_skillselect.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add src/koshi/extraction/skillselect_rounds.py tests/test_extraction_skillselect.py tests/fixtures/skillselect_rounds_sample_malformed.html
git commit -m "Add per-row isolation and loose int parsing to the SkillSelect parser"
```

---

### Task 7: `pipeline.py` — adapt to `ParseResult` + isolate the momentum-refresh loop

**Files:**
- Modify: `src/koshi/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `ParseResult` from both parsers (Tasks 5, 6) — `sync_anzsco_occupations`/`sync_skillselect_rounds` now read `.rows` (and log `.skipped` when non-zero) instead of treating the parser's return value as a bare list.
- Produces: no interface changes — `sync_anzsco_occupations(session, *, url=..., client=...) -> list[Occupation]` and `sync_skillselect_rounds(session, *, url=..., visa_code=..., client=...) -> list[EoiRound]` keep their existing signatures and return types (still plain lists of persisted rows, not `ParseResult` — that type is internal to the parsers).

- [ ] **Step 1: Write the failing test — momentum-loop isolation**

```python
# tests/test_pipeline.py — add
import httpx
from sqlalchemy import select

import koshi.pipeline as pipeline_module
from koshi.models.occupation_momentum import OccupationMomentum


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pipeline.py -v -k momentum_refresh_failure`
Expected: FAIL — today, `flaky_refresh` raising `RuntimeError` propagates straight out of `sync_skillselect_rounds`, so the test's `result = pipeline_module.sync_skillselect_rounds(...)` line itself raises instead of returning.

- [ ] **Step 3: Update `pipeline.py`**

```python
# src/koshi/pipeline.py
import datetime as dt
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.anzsco_occupations import parse_anzsco_occupations
from koshi.extraction.skillselect_rounds import parse_skillselect_rounds
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupations import Occupation
from koshi.models.source_pages import SourcePage
from koshi.momentum import refresh_momentum

logger = logging.getLogger(__name__)

ANZSCO_URL = "https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco"
SKILLSELECT_ROUNDS_URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"

_NEVER_EXTRACTED = dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _needs_extraction(page: SourcePage) -> bool:
    """Whether this page's content has changed since it was last
    successfully parsed.

    Deliberately NOT the `changed` bool fetch_and_register returns:
    fetch_and_register commits content_hash/last_changed_at before parsing
    is even attempted, so if parsing raised last time, `changed` would be
    False on the next run (the hash hasn't moved) and the page would be
    silently skipped forever. Comparing last_changed_at against our own
    last_extracted_at watermark instead means a prior parse failure (which
    leaves last_extracted_at untouched) is retried on every subsequent run.
    """
    watermark = page.last_extracted_at or _NEVER_EXTRACTED
    return page.last_changed_at > watermark


def sync_anzsco_occupations(
    session: Session, *, url: str = ANZSCO_URL, client: httpx.Client | None = None
) -> list[Occupation]:
    page, _changed, text = fetch_and_register(
        session, url=url, domain="www.jobsandskills.gov.au", category="anzsco_occupations", client=client
    )
    if not _needs_extraction(page):
        return []

    result = parse_anzsco_occupations(
        text, source_url=url, retrieved_at=dt.datetime.now(dt.timezone.utc)
    )
    if result.skipped:
        logger.warning("anzsco_occupations: skipped %d malformed row(s)", result.skipped)
    for occupation in result.rows:
        session.merge(occupation)
    # Only advance the extraction watermark once parsing AND persisting
    # have both succeeded — if parse_anzsco_occupations raised above, this
    # line (and the commit) never runs, so the next sync retries.
    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return result.rows


def sync_skillselect_rounds(
    session: Session,
    *,
    url: str = SKILLSELECT_ROUNDS_URL,
    visa_code: str = "189",
    client: httpx.Client | None = None,
) -> list[EoiRound]:
    page, _changed, text = fetch_and_register(
        session, url=url, domain="immi.homeaffairs.gov.au", category="skillselect_rounds", client=client
    )
    if not _needs_extraction(page):
        return []

    parse_result = parse_skillselect_rounds(
        text,
        visa_code=visa_code,
        source_url=url,
        retrieved_at=dt.datetime.now(dt.timezone.utc),
    )
    if parse_result.skipped:
        logger.warning("skillselect_rounds: skipped %d malformed row(s)", parse_result.skipped)

    # Upsert by (visa_code, occupation_code, round_date): a whole-page hash
    # change (build stamp, "last reviewed" date) re-parses the same round
    # data and must not manufacture duplicate rows / fake momentum.
    #
    # The DB existence check alone isn't enough to dedup rows *within* this
    # same batch: the production session (koshi.db.SessionLocal) sets
    # autoflush=False, so an earlier session.add() in this loop is never
    # flushed before the next iteration's SELECT runs. Tracking keys
    # already staged in this call closes that gap.
    new_rounds = []
    staged_keys: set[tuple[str, str | None, dt.date]] = set()
    for round_ in parse_result.rows:
        key = (round_.visa_code, round_.occupation_code, round_.round_date)
        if key in staged_keys:
            continue
        existing = session.scalar(
            select(EoiRound).where(
                EoiRound.visa_code == round_.visa_code,
                EoiRound.occupation_code == round_.occupation_code,
                EoiRound.round_date == round_.round_date,
            )
        )
        if existing is not None:
            continue
        session.add(round_)
        staged_keys.add(key)
        new_rounds.append(round_)
    # Only advance the extraction watermark once parsing AND persisting
    # have both succeeded — see sync_anzsco_occupations above.
    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()

    # Recompute momentum for every occupation touched by a genuinely new
    # round. Isolated per code: one occupation's momentum computation
    # failing must not prevent the others from being refreshed, and must
    # not undo the round persistence that already committed above.
    new_codes = {r.occupation_code for r in new_rounds if r.occupation_code is not None}
    for code in new_codes:
        try:
            refresh_momentum(session, code)
        except Exception:
            logger.exception("momentum refresh failed for occupation_code=%s", code)

    return new_rounds
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `.venv/bin/pytest tests/test_pipeline.py -v -k momentum_refresh_failure`
Expected: PASS

- [ ] **Step 5: Run the full pipeline test file to verify nothing else broke**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: PASS (all tests — the pre-existing sync tests still pass since `sync_anzsco_occupations`/`sync_skillselect_rounds`'s public return types are unchanged, only their internal handling of the now-`ParseResult` parser output changed)

- [ ] **Step 6: Commit**

```bash
git add src/koshi/pipeline.py tests/test_pipeline.py
git commit -m "Adapt pipeline.py to ParseResult; isolate the momentum-refresh loop"
```

---

### Task 8: `seeds/loader.py` — generalize + per-entry isolation

**Files:**
- Modify: `src/koshi/seeds/loader.py`
- Modify: `tests/test_ceiling_seed_loader.py`

**Interfaces:**
- Consumes: `koshi.resilience.isolated_item` (Task 2).
- Produces: `koshi.seeds.loader.load_seed_rows(path: Path, *, row_builder: Callable[[dict], Any]) -> tuple[list, int]` — a generalized per-entry-isolated YAML loader, ready for the ~7 tier-5 sources Phase 2 will add.
- Produces (unchanged signatures, changed internal behavior): `load_ceiling_usage_seed(path: Path) -> list[CeilingUsage]` — **now skips an invalid entry instead of raising**; `seed_ceiling_usage(session: Session, path: Path) -> list[CeilingUsage]` — internals now use `isolated_item` per row.

- [ ] **Step 1: Update the existing provenance-rejection test for the new skip-based behavior**

The existing test asserted the loader *raises* `ProvenanceError` on a bad row. Per-entry isolation means it now *skips* that row and keeps the good ones — replace the test:

```python
# tests/test_ceiling_seed_loader.py — replace test_rejects_row_missing_source_url with:
def test_skips_invalid_row_but_loads_other_valid_rows_in_the_same_file(tmp_path):
    seed_file = tmp_path / "seed.yaml"
    seed_file.write_text(
        """
- occupation_code: "261313"
  program_year: "2025-26"
  issued: 3200
  ceiling: 5000
  as_of_date: "2026-07-31"
  source_url: ""
  retrieved_at: "2026-08-01T00:00:00+00:00"
- occupation_code: "254499"
  program_year: "2025-26"
  issued: 1800
  ceiling: 4000
  as_of_date: "2026-07-31"
  source_url: "https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels"
  retrieved_at: "2026-08-01T00:00:00+00:00"
"""
    )

    rows = load_ceiling_usage_seed(seed_file)

    assert len(rows) == 1
    assert rows[0].occupation_code == "254499"
```

Keep the existing `test_loads_one_row_from_seed_file` test unchanged — it doesn't exercise any invalid rows.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ceiling_seed_loader.py -v -k skips_invalid_row`
Expected: FAIL — today's loader raises `ProvenanceError` for the whole file instead of skipping the one bad row.

- [ ] **Step 3: Write the failing test for `seed_ceiling_usage`'s DB-level per-row isolation**

```python
# tests/test_ceiling_seed_loader.py — add
import datetime as dt

from koshi.models.ceiling_usage import CeilingUsage
from koshi.models.occupations import Occupation
from koshi.seeds.loader import seed_ceiling_usage


def test_seed_ceiling_usage_persists_valid_rows_even_if_one_violates_an_fk_constraint(
    db_session, tmp_path
):
    db_session.add(
        Occupation(
            code="254499", name="Registered Nurse (Aged Care)", unit_group="2544",
            source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()

    seed_file = tmp_path / "seed.yaml"
    seed_file.write_text(
        """
- occupation_code: "999999"
  program_year: "2025-26"
  issued: 3200
  ceiling: 5000
  as_of_date: "2026-07-31"
  source_url: "https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels"
  retrieved_at: "2026-08-01T00:00:00+00:00"
- occupation_code: "254499"
  program_year: "2025-26"
  issued: 1800
  ceiling: 4000
  as_of_date: "2026-07-31"
  source_url: "https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels"
  retrieved_at: "2026-08-01T00:00:00+00:00"
"""
    )

    rows = seed_ceiling_usage(db_session, seed_file)

    assert len(rows) == 1
    assert rows[0].occupation_code == "254499"

    persisted = db_session.query(CeilingUsage).filter_by(occupation_code="254499").one()
    assert persisted.issued == 1800
```

`"999999"` has no matching `Occupation` row, so persisting its `CeilingUsage` row violates the foreign key — proving `isolated_item`'s SAVEPOINT genuinely isolates a DB-level failure, not just a Python-level validation error (already covered by Step 1's test).

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ceiling_seed_loader.py -v -k fk_constraint`
Expected: FAIL — today, the FK violation raises out of `seed_ceiling_usage` entirely, and no row (including the valid `"254499"` one) gets persisted, since the whole transaction aborts.

- [ ] **Step 5: Rewrite `seeds/loader.py`**

```python
# src/koshi/seeds/loader.py
import datetime as dt
import logging
from pathlib import Path
from typing import Any, Callable

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.models.ceiling_usage import CeilingUsage
from koshi.provenance import require_provenance
from koshi.resilience import isolated_item

logger = logging.getLogger(__name__)


def load_seed_rows(path: Path, *, row_builder: Callable[[dict], Any]) -> tuple[list, int]:
    """Load entries from a YAML seed file, building one row per entry via
    row_builder. A bad entry (missing key, bad value, failed provenance or
    data-shape validation) is logged and skipped rather than aborting
    every other valid entry in the same file — a curation typo on one
    occupation shouldn't block the rest of the seed.
    """
    entries = yaml.safe_load(path.read_text())
    rows = []
    skipped = 0
    for index, entry in enumerate(entries):
        try:
            rows.append(row_builder(entry))
        except (KeyError, ValueError) as exc:
            logger.warning("skipping seed entry %d in %s: %r", index, path.name, exc)
            skipped += 1
    return rows, skipped


def _build_ceiling_usage_row(entry: dict) -> CeilingUsage:
    retrieved_at = dt.datetime.fromisoformat(entry["retrieved_at"])
    require_provenance(
        reliability_tier="official_curated",
        source_url=entry["source_url"],
        retrieved_at=retrieved_at,
    )

    # Data-shape sanity, mirrored by the DB-level
    # ck_ceiling_usage_issued_within_ceiling CHECK constraint — fail fast
    # here with a clear error instead of relying on the DB round-trip.
    issued = entry["issued"]
    ceiling = entry["ceiling"]
    if ceiling <= 0:
        raise ValueError(f"{entry['occupation_code']!r}: ceiling must be > 0, got {ceiling!r}")
    if issued > ceiling:
        raise ValueError(
            f"{entry['occupation_code']!r}: issued ({issued}) exceeds ceiling ({ceiling})"
        )

    return CeilingUsage(
        occupation_code=entry["occupation_code"],
        program_year=entry["program_year"],
        issued=issued,
        ceiling=ceiling,
        as_of_date=dt.date.fromisoformat(entry["as_of_date"]),
        source_url=entry["source_url"],
        retrieved_at=retrieved_at,
        reliability_tier="official_curated",
    )


def load_ceiling_usage_seed(path: Path) -> list[CeilingUsage]:
    """Thin wrapper over load_seed_rows — preserves the original
    signature every existing caller/test uses."""
    rows, _skipped = load_seed_rows(path, row_builder=_build_ceiling_usage_row)
    return rows


def seed_ceiling_usage(session: Session, path: Path) -> list[CeilingUsage]:
    """Load the ceiling_usage seed file and persist any rows not already
    in the database.

    Upserts by (occupation_code, program_year, as_of_date) so re-running
    the seed doesn't manufacture duplicate rows. Each row's persistence is
    scoped in isolated_item — a DB-level failure (e.g. an unresolvable FK)
    on one row must not prevent other valid rows in the same file from
    landing.
    """
    rows = load_ceiling_usage_seed(path)

    new_rows = []
    for row in rows:
        with isolated_item(session, f"ceiling_usage seed for {row.occupation_code}"):
            existing = session.scalar(
                select(CeilingUsage).where(
                    CeilingUsage.occupation_code == row.occupation_code,
                    CeilingUsage.program_year == row.program_year,
                    CeilingUsage.as_of_date == row.as_of_date,
                )
            )
            if existing is not None:
                continue
            session.add(row)
            new_rows.append(row)
    session.commit()
    return new_rows
```

- [ ] **Step 6: Run all tests in the file to verify they pass**

Run: `.venv/bin/pytest tests/test_ceiling_seed_loader.py -v`
Expected: PASS (all tests)

- [ ] **Step 7: Run the full suite to check for ripple effects**

Run: `.venv/bin/pytest -v`
Expected: PASS — in particular, confirm `tests/test_api_occupation_detail.py`'s
`test_seeded_ceiling_usage_is_actually_servable_end_to_end` (if present) and
any other test calling `seed_ceiling_usage`/`load_ceiling_usage_seed` still pass.

- [ ] **Step 8: Commit**

```bash
git add src/koshi/seeds/loader.py tests/test_ceiling_seed_loader.py
git commit -m "Generalize seed loading with per-entry isolation (load_seed_rows, isolated_item)"
```

---

### Task 9: `__main__.py` — per-step isolation, rollback, exit codes, run-summary wiring

**Files:**
- Modify: `src/koshi/__main__.py`
- Create: `tests/test_main.py`

**Interfaces:**
- Consumes: `koshi.logging_config.setup_logging` (Task 1), `koshi.run_summary.write_run_summary` (Task 3), `koshi.pipeline.sync_anzsco_occupations`/`sync_skillselect_rounds` (Task 7, unchanged signatures), `koshi.seeds.loader.seed_ceiling_usage` (Task 8, unchanged signature).
- Produces: `koshi.__main__.main() -> int` — **return type changed** from `None` to `int` (an exit code: `0`/`2`/`3` reachable by this plan's steps, `1` reserved for a fatal init failure no step in this plan triggers). `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_main.py
import koshi.__main__ as main_module


class _FakeSession:
    """Stands in for SessionLocal() in these tests — the sync/seed
    functions are monkeypatched below and never touch it, so a real DB
    connection isn't needed to test main()'s control flow."""

    def rollback(self):
        pass

    def close(self):
        pass


def test_main_returns_0_when_all_steps_succeed(monkeypatch):
    monkeypatch.setattr(main_module, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(main_module, "sync_anzsco_occupations", lambda session: [1, 2])
    monkeypatch.setattr(main_module, "sync_skillselect_rounds", lambda session: [1])
    monkeypatch.setattr(main_module, "seed_ceiling_usage", lambda session, path: [1, 2, 3])

    exit_code = main_module.main()

    assert exit_code == 0


def test_main_returns_2_and_still_runs_remaining_steps_when_one_step_fails(monkeypatch):
    calls = []

    def failing_sync(session):
        calls.append("anzsco")
        raise RuntimeError("boom")

    def ok_sync(session):
        calls.append("skillselect")
        return [1]

    def ok_seed(session, path):
        calls.append("ceiling")
        return [1]

    monkeypatch.setattr(main_module, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(main_module, "sync_anzsco_occupations", failing_sync)
    monkeypatch.setattr(main_module, "sync_skillselect_rounds", ok_sync)
    monkeypatch.setattr(main_module, "seed_ceiling_usage", ok_seed)

    exit_code = main_module.main()

    assert exit_code == 2
    assert calls == ["anzsco", "skillselect", "ceiling"]


def test_main_returns_3_when_all_steps_fail(monkeypatch):
    def failing(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(main_module, "sync_anzsco_occupations", failing)
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


def test_main_writes_a_run_summary_reflecting_each_steps_outcome(monkeypatch):
    written = {}

    def fake_write_run_summary(summary):
        written["summary"] = summary
        return "fake-path"

    monkeypatch.setattr(main_module, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(main_module, "sync_anzsco_occupations", lambda session: [1])
    monkeypatch.setattr(main_module, "sync_skillselect_rounds", lambda session: [])
    monkeypatch.setattr(main_module, "seed_ceiling_usage", lambda session, path: [])
    monkeypatch.setattr(main_module, "write_run_summary", fake_write_run_summary)

    main_module.main()

    assert "summary" in written
    assert written["summary"]["steps"][0] == {"name": "anzsco_occupations", "status": "ok", "count": 1}
    assert written["summary"]["steps"][1] == {"name": "skillselect_rounds", "status": "ok", "count": 0}
    assert written["summary"]["steps"][2] == {"name": "ceiling_usage_seed", "status": "ok", "count": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_main.py -v`
Expected: FAIL — `main()` currently returns `None`, not an `int`, and takes no exit-code path at all.

- [ ] **Step 3: Rewrite `__main__.py`**

```python
# src/koshi/__main__.py
"""Runnable entry point for koshi's full local sync.

Usage (after `alembic upgrade head`):

    python -m koshi

Runs, in order:
1. sync_anzsco_occupations — occupations must exist first: eoi_rounds and
   ceiling_usage rows both carry a FK to occupations.code.
2. sync_skillselect_rounds — persists new EOI rounds and (per pipeline.py)
   refreshes occupation_momentum for every occupation a new round touches.
3. seed_ceiling_usage — persists the manually-curated ceiling data shipped
   in seeds/ceiling_usage_manual.yaml.

Each step is isolated: a failure in one is logged and recorded in the run
summary, but does NOT prevent the remaining steps from running — e.g.
seed_ceiling_usage has zero dependency on either scraping step succeeding
and must still run even if both of them fail.

Exit codes: 0 clean, 1 fatal init failure (not reachable by any step
above — reserved for e.g. an unreachable database before the loop starts),
2 partial failure (some steps ok, some failed — the expected common state
once there are many sources, not a rare edge case), 3 total failure (every
step failed). A cron wrapper (and later, Cloud Scheduler + Cloud
Monitoring) can act on 2/3 without koshi needing any notification
integration built — see the ETL finalization design doc §8.
"""
import logging
import sys
import datetime as dt
from pathlib import Path

from koshi.db import SessionLocal
from koshi.logging_config import setup_logging
from koshi.pipeline import sync_anzsco_occupations, sync_skillselect_rounds
from koshi.run_summary import write_run_summary
from koshi.seeds.loader import seed_ceiling_usage

CEILING_USAGE_SEED_PATH = Path(__file__).parent / "seeds" / "ceiling_usage_manual.yaml"


def main() -> int:
    setup_logging()
    logger = logging.getLogger(__name__)
    try:
        session = SessionLocal()
    except Exception:
        logger.exception("fatal: could not initialize a database session")
        return 1

    summary: dict = {
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "steps": [],
    }

    steps = [
        ("anzsco_occupations", lambda: sync_anzsco_occupations(session)),
        ("skillselect_rounds", lambda: sync_skillselect_rounds(session)),
        ("ceiling_usage_seed", lambda: seed_ceiling_usage(session, CEILING_USAGE_SEED_PATH)),
    ]

    try:
        for name, step in steps:
            try:
                result = step()
                summary["steps"].append({"name": name, "status": "ok", "count": len(result)})
                logger.info("%s: %d new/updated", name, len(result))
            except Exception:
                session.rollback()
                logger.exception("%s failed — continuing with remaining steps", name)
                summary["steps"].append({"name": name, "status": "failed"})
    finally:
        session.close()

    write_run_summary(summary)

    ok = sum(1 for s in summary["steps"] if s["status"] == "ok")
    failed = sum(1 for s in summary["steps"] if s["status"] == "failed")
    if failed and ok == 0:
        return 3
    if failed:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_main.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/koshi/__main__.py tests/test_main.py
git commit -m "Isolate __main__.py's 3 sync steps; add exit codes and run-summary wiring"
```

---

### Task 10: `.gitignore` + final full-suite verification

**Files:**
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this task closes out the phase.

- [ ] **Step 1: Add `logs/` to `.gitignore`**

```
# .gitignore — add under the "Python" section, alongside .pytest_cache/
logs/
```

- [ ] **Step 2: Confirm the log/summary directories are actually ignored**

Run: `git status --short` after having run `python -m koshi` at least once locally (or after running the test suite, which exercises `logging_config`/`run_summary`) — `logs/` must not appear as untracked.

- [ ] **Step 3: Run the full suite one final time**

Run: `.venv/bin/pytest -v`
Expected: PASS — every test from this plan plus every pre-existing test (baseline 51, this plan adds: 1 logging test, 7 resilience tests, 1 run_summary test, 3 new crawler_fetch tests, 1 new anzsco malformed-row test, 1 new skillselect malformed-row test, 1 momentum-isolation test, 2 new seed-loader tests, 5 new `__main__` tests — replacing 1 old seed-loader test — net new: ~22 tests, so expect roughly 73 passing; the exact count doesn't matter as much as zero failures).

- [ ] **Step 4: Run a real end-to-end sync locally to confirm the retrofit works outside of mocks**

Run: `DATABASE_URL=postgresql+psycopg://koshi:koshi@localhost:5432/koshi .venv/bin/python -m koshi`
Expected: exits `0` (or `2` if a real government page has changed shape since this plan was written — check `logs/koshi.log` and the newest file in `logs/summaries/` either way, both should now exist and contain real content, unlike before this plan).

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "Ignore logs/; close out the fault-tolerance retrofit (Phase 0)"
```
