# koshi — Occupation Data Slice (v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up koshi's first working vertical slice — the Occupation view — end to end, on the architecture the 2026-08-14 design spec settled on: koshi's own crawler discovers and hashes its source pages (no external crawler repo, no Notion), deterministic parsers extract real facts from two of them, a manual-curation seed fills the one table extraction can't reach yet, momentum is computed (not scraped), and `GET /v1/occupations` + `GET /v1/occupations/{code}` serve all of it with `reliability_tier`/`retrieved_at` on every fact.

**Architecture:** FastAPI + SQLAlchemy 2.0 + Alembic against local Postgres (Docker Compose). Five tables (`source_pages`, `occupations`, `eoi_rounds`, `ceiling_usage`, `occupation_momentum`), koshi's own httpx + BeautifulSoup crawler and extraction tiers, deterministic insight templates, two REST endpoints. No Cloud SQL, no Terraform, no Cloud Run in this plan — deliberately deferred per the design spec §11.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, Postgres 16 (Docker Compose locally), httpx, BeautifulSoup4 + lxml, PyYAML, pytest.

**Reference:** `docs/superpowers/specs/2026-08-14-koshi-design.md` — this plan builds §3.1 (`occupations`), §3.2 (`eoi_rounds`, `ceiling_usage`), §3.3 (`occupation_momentum`), §5 (crawl tier 1, extraction tiers 2 and 5), and the `/v1/occupations` and `/v1/occupations/{code}` parts of §6. State, visa comparison, national, and reference endpoints are separate future plans — not in scope here.

## Global Constraints

- Every fact-bearing row carries `source_url`, `retrieved_at`, `reliability_tier` — enforced by `koshi.provenance.require_provenance()` before insert, except rows with `reliability_tier="derived"`, which carry no `source_url` (design spec §3).
- `reliability_tier` values used in this plan: `official_scraped` (deterministic parser), `official_curated` (manual seed against a real cited source), `derived` (computed inside koshi from koshi's own rows). No `community_sourced` rows in this slice.
- No LLM/Claude fallback in this plan. Both pages this slice targets (SkillSelect rounds, the ANZSCO occupation list) are template-parseable; Claude fallback is a later slice's task (design spec §5 tier 4).
- API is versioned under `/v1`, OpenAPI-first — FastAPI's generated schema at `/v1/openapi.json` is the contract (design spec §6).
- No end-user identity anywhere in this service (design spec §8) — no auth code anywhere in this plan.
- No response field or generated string may use eligibility/advice language ("you should/can/are eligible/will") — Task 10's phrase-ban test is the enforcement point (design spec §7).
- Local-first: every task runs against Docker Compose Postgres. No Cloud SQL, no Terraform, no Cloud Run — out of scope for this entire plan (design spec §9, §11).

---

### Task 1: Project scaffold — FastAPI app, Docker Compose Postgres, healthz

**Files:**
- Create: `pyproject.toml`
- Create: `docker-compose.yml`
- Create: `src/koshi/__init__.py`
- Create: `src/koshi/main.py`
- Create: `src/koshi/db.py`
- Test: `tests/test_healthz.py`

**Interfaces:**
- Produces: `koshi.main.app` (the FastAPI instance every later task's router attaches to), `koshi.db.Base` (declarative base every model inherits from), `koshi.db.make_engine(database_url: str | None) -> Engine`, `koshi.db.get_session()` (FastAPI dependency, yields a `Session`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_healthz.py
from fastapi.testclient import TestClient
from koshi.main import app


def test_healthz_returns_ok():
    client = TestClient(app)
    response = client.get("/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_healthz.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'koshi'`

- [ ] **Step 3: Write the scaffold**

```toml
# pyproject.toml
[project]
name = "koshi"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.2",
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "lxml>=5.2",
    "pyyaml>=6.0",
    "pydantic>=2.8",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: koshi
      POSTGRES_PASSWORD: koshi
      POSTGRES_DB: koshi
    ports:
      - "5432:5432"
    volumes:
      - koshi_pgdata:/var/lib/postgresql/data

volumes:
  koshi_pgdata:
```

```python
# src/koshi/db.py
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str | None = None):
    url = database_url or os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://koshi:koshi@localhost:5432/koshi"
    )
    return create_engine(url, future=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

```python
# src/koshi/main.py
from fastapi import FastAPI

app = FastAPI(title="koshi", version="0.1.0", openapi_url="/v1/openapi.json", docs_url="/v1/docs")


@app.get("/v1/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

Install: `pip install -e ".[dev]"`

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_healthz.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml docker-compose.yml src/koshi/__init__.py src/koshi/main.py src/koshi/db.py tests/test_healthz.py
git commit -m "Scaffold koshi: FastAPI app, Docker Compose Postgres, healthz"
```

---

### Task 2: `source_pages` table — the crawl registry (Alembic setup + model)

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_create_source_pages.py`
- Create: `src/koshi/models/__init__.py`
- Create: `src/koshi/models/source_pages.py`
- Create: `tests/conftest.py`
- Test: `tests/test_source_pages_model.py`

**Interfaces:**
- Consumes: `koshi.db.Base`, `koshi.db.make_engine` (Task 1).
- Produces: `koshi.models.source_pages.SourcePage` (columns: `id`, `url`, `domain`, `category`, `content_hash`, `first_seen_at`, `last_checked_at`, `last_changed_at`, `status`) — Task 3's crawler reads/writes this.
- Produces: `tests/conftest.py`'s `db_session` fixture — every later DB-touching test in this plan uses it.

- [ ] **Step 1: Create the test Postgres database**

Run: `docker compose up -d postgres` then `docker compose exec postgres createdb -U koshi koshi_test`

- [ ] **Step 2: Write the failing test**

```python
# tests/conftest.py
import os

import pytest
from sqlalchemy.orm import sessionmaker

from koshi.db import Base, make_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://koshi:koshi@localhost:5432/koshi_test"
)


@pytest.fixture(scope="session")
def engine():
    eng = make_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    yield session
    session.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()
```

```python
# tests/test_source_pages_model.py
from koshi.models.source_pages import SourcePage


def test_insert_and_read_source_page(db_session):
    page = SourcePage(
        url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
        domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds",
        content_hash="abc123",
        status="active",
    )
    db_session.add(page)
    db_session.commit()

    found = db_session.query(SourcePage).filter_by(url=page.url).one()
    assert found.domain == "immi.homeaffairs.gov.au"
    assert found.status == "active"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_source_pages_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'koshi.models'`

- [ ] **Step 4: Write the model and migration**

```python
# src/koshi/models/__init__.py
```

```python
# src/koshi/models/source_pages.py
import datetime as dt

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class SourcePage(Base):
    """The crawl registry — replaces the old research/au-visa-sources +
    Notion pair (design spec §5). Metadata about a page, not a fact: no
    reliability_tier/source_url here, because this table *is* the source."""

    __tablename__ = "source_pages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_checked_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_changed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
```

```ini
# alembic.ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+psycopg://koshi:koshi@localhost:5432/koshi

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

```python
# alembic/env.py
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from koshi.db import Base
import koshi.models.source_pages  # noqa: F401 — registers the table on Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("DATABASE_URL", "postgresql+psycopg://koshi:koshi@localhost:5432/koshi"),
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

```python
# alembic/versions/0001_create_source_pages.py
"""create source_pages

Revision ID: 0001
Revises:
Create Date: 2026-08-14
"""
import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_pages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("url", sa.String, nullable=False, unique=True),
        sa.Column("domain", sa.String, nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("content_hash", sa.String, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.String, nullable=False, server_default="active"),
    )


def downgrade() -> None:
    op.drop_table("source_pages")
```

Run: `DATABASE_URL=postgresql+psycopg://koshi:koshi@localhost:5432/koshi alembic upgrade head`

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_source_pages_model.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add alembic.ini alembic/ src/koshi/models/ tests/conftest.py tests/test_source_pages_model.py
git commit -m "Add source_pages table — koshi's own crawl registry (Alembic setup)"
```

---

### Task 3: Crawler — fetch, hash, and register change-detection

**Files:**
- Create: `src/koshi/crawler/__init__.py`
- Create: `src/koshi/crawler/fetch.py`
- Test: `tests/test_crawler_fetch.py`

**Interfaces:**
- Consumes: `koshi.models.source_pages.SourcePage` (Task 2).
- Produces: `koshi.crawler.fetch.hash_content(content: bytes) -> str`, `koshi.crawler.fetch.fetch_and_register(session, *, url, domain, category, client=None) -> tuple[SourcePage, bool, bytes]` — `changed` and the raw `content` bytes are what Task 13's pipeline uses to avoid fetching each page twice (once to hash, once to parse).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_crawler_fetch.py
import httpx

from koshi.crawler.fetch import fetch_and_register, hash_content

URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"


def _client_returning(body: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_new_page_is_registered_as_changed(db_session):
    body = b"<html>version one</html>"
    page, changed, content = fetch_and_register(
        db_session,
        url=URL,
        domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds",
        client=_client_returning(body),
    )
    assert changed is True
    assert page.content_hash == hash_content(body)
    assert content == body


def test_unchanged_page_is_not_flagged_changed(db_session):
    body = b"<html>version one</html>"
    fetch_and_register(
        db_session, url=URL, domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds", client=_client_returning(body),
    )

    page, changed, content = fetch_and_register(
        db_session, url=URL, domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds", client=_client_returning(body),
    )
    assert changed is False


def test_changed_page_is_flagged_changed(db_session):
    fetch_and_register(
        db_session, url=URL, domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds", client=_client_returning(b"<html>version one</html>"),
    )

    page, changed, content = fetch_and_register(
        db_session, url=URL, domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds", client=_client_returning(b"<html>version TWO</html>"),
    )
    assert changed is True
    assert page.content_hash == hash_content(b"<html>version TWO</html>")
    assert content == b"<html>version TWO</html>"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_crawler_fetch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'koshi.crawler'`

- [ ] **Step 3: Write the implementation**

```python
# src/koshi/crawler/__init__.py
```

```python
# src/koshi/crawler/fetch.py
import datetime as dt
import hashlib

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.models.source_pages import SourcePage


def hash_content(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def fetch_and_register(
    session: Session,
    *,
    url: str,
    domain: str,
    category: str,
    client: httpx.Client | None = None,
) -> tuple[SourcePage, bool, bytes]:
    """Fetch a page, hash it, and upsert into source_pages.

    Returns (page, changed, content). changed is True for a brand-new page
    or one whose content_hash differs from what's stored. content is the
    raw response body — callers that need to parse the page (Task 13) reuse
    it instead of fetching a second time.
    """
    owns_client = client is None
    active_client = client or httpx.Client(timeout=15.0)
    try:
        response = active_client.get(url)
        response.raise_for_status()
        content = response.content
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
        return page, True, content

    changed = existing.content_hash != content_hash
    existing.last_checked_at = now
    if changed:
        existing.content_hash = content_hash
        existing.last_changed_at = now
    session.commit()
    return existing, changed, content
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_crawler_fetch.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/koshi/crawler/ tests/test_crawler_fetch.py
git commit -m "Add crawler fetch + change-detection against source_pages"
```

---

### Task 4: `occupations` table + provenance helper

**Files:**
- Create: `src/koshi/provenance.py`
- Create: `src/koshi/models/occupations.py`
- Create: `alembic/versions/0002_create_occupations.py`
- Test: `tests/test_provenance.py`
- Test: `tests/test_occupations_model.py`

**Interfaces:**
- Produces: `koshi.provenance.ProvenanceError`, `koshi.provenance.require_provenance(*, reliability_tier: str, source_url: str | None) -> None` — every extraction task from here on (5, 7, 8) calls this before insert.
- Produces: `koshi.models.occupations.Occupation` (columns: `code` PK, `name`, `unit_group`, `source_url`, `retrieved_at`, `reliability_tier`) — Task 5 populates it, Tasks 6–12 reference `occupation_code` against it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_provenance.py
import pytest

from koshi.provenance import ProvenanceError, require_provenance


def test_derived_tier_does_not_require_source_url():
    require_provenance(reliability_tier="derived", source_url=None)  # must not raise


def test_official_scraped_requires_source_url():
    with pytest.raises(ProvenanceError):
        require_provenance(reliability_tier="official_scraped", source_url=None)


def test_official_curated_requires_non_empty_source_url():
    with pytest.raises(ProvenanceError):
        require_provenance(reliability_tier="official_curated", source_url="")
```

```python
# tests/test_occupations_model.py
import datetime as dt

from koshi.models.occupations import Occupation


def test_insert_and_read_occupation(db_session):
    occupation = Occupation(
        code="261313",
        name="Software Engineer",
        unit_group="2613 Software and Applications Programmers",
        source_url="https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco",
        retrieved_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
        reliability_tier="official_scraped",
    )
    db_session.add(occupation)
    db_session.commit()

    found = db_session.get(Occupation, "261313")
    assert found.name == "Software Engineer"
    assert found.reliability_tier == "official_scraped"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_provenance.py tests/test_occupations_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'koshi.provenance'`

- [ ] **Step 3: Write the implementation**

```python
# src/koshi/provenance.py
class ProvenanceError(ValueError):
    """Raised when a fact-bearing row would be inserted without the
    provenance the design spec §3 requires."""


def require_provenance(*, reliability_tier: str, source_url: str | None) -> None:
    if reliability_tier == "derived":
        return
    if not source_url:
        raise ProvenanceError(
            f"reliability_tier={reliability_tier!r} requires a non-empty source_url"
        )
```

```python
# src/koshi/models/occupations.py
import datetime as dt

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class Occupation(Base):
    __tablename__ = "occupations"

    code: Mapped[str] = mapped_column(String, primary_key=True)  # ANZSCO code
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit_group: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
```

```python
# alembic/versions/0002_create_occupations.py
"""create occupations

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-14
"""
import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "occupations",
        sa.Column("code", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("unit_group", sa.String, nullable=False),
        sa.Column("source_url", sa.String, nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String, nullable=False, server_default="official_scraped"),
    )


def downgrade() -> None:
    op.drop_table("occupations")
```

Update `alembic/env.py`'s imports to also register this model: add `import koshi.models.occupations  # noqa: F401` next to the `source_pages` import.

Run: `DATABASE_URL=postgresql+psycopg://koshi:koshi@localhost:5432/koshi alembic upgrade head`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_provenance.py tests/test_occupations_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/koshi/provenance.py src/koshi/models/occupations.py alembic/versions/0002_create_occupations.py alembic/env.py tests/test_provenance.py tests/test_occupations_model.py
git commit -m "Add occupations table and the provenance helper every extractor uses"
```

---

### Task 5: ANZSCO occupation-list extraction parser

**Files:**
- Create: `src/koshi/extraction/__init__.py`
- Create: `src/koshi/extraction/anzsco_occupations.py`
- Test: `tests/fixtures/anzsco_sample.html`
- Test: `tests/test_extraction_anzsco.py`

**Interfaces:**
- Consumes: `koshi.provenance.require_provenance`, `koshi.models.occupations.Occupation` (Task 4).
- Produces: `koshi.extraction.anzsco_occupations.parse_anzsco_occupations(html: str, *, source_url: str, retrieved_at: dt.datetime) -> list[Occupation]` — unpersisted model instances; the caller (Task 13's seed script, or a future scheduled job) adds and commits them.

- [ ] **Step 1: Write the fixture and the failing test**

```html
<!-- tests/fixtures/anzsco_sample.html -->
<table id="occupation-list">
  <thead><tr><th>ANZSCO Code</th><th>Occupation</th><th>Unit Group</th></tr></thead>
  <tbody>
    <tr><td>261313</td><td>Software Engineer</td><td>2613 Software and Applications Programmers</td></tr>
    <tr><td>254499</td><td>Registered Nurse (Aged Care)</td><td>2544 Registered Nurses</td></tr>
  </tbody>
</table>
```

```python
# tests/test_extraction_anzsco.py
import datetime as dt
from pathlib import Path

from koshi.extraction.anzsco_occupations import parse_anzsco_occupations

FIXTURE = (Path(__file__).parent / "fixtures" / "anzsco_sample.html").read_text()
SOURCE_URL = "https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco"
RETRIEVED_AT = dt.datetime(2026, 8, 14, tzinfo=dt.timezone.utc)


def test_parses_two_occupations_from_fixture():
    result = parse_anzsco_occupations(FIXTURE, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT)

    assert len(result) == 2
    swe = next(o for o in result if o.code == "261313")
    assert swe.name == "Software Engineer"
    assert swe.unit_group == "2613 Software and Applications Programmers"
    assert swe.reliability_tier == "official_scraped"
    assert swe.source_url == SOURCE_URL
    assert swe.retrieved_at == RETRIEVED_AT


def test_persists_parsed_occupations(db_session):
    result = parse_anzsco_occupations(FIXTURE, source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT)
    db_session.add_all(result)
    db_session.commit()

    from koshi.models.occupations import Occupation

    found = db_session.get(Occupation, "254499")
    assert found.name == "Registered Nurse (Aged Care)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extraction_anzsco.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'koshi.extraction'`

- [ ] **Step 3: Write the parser**

```python
# src/koshi/extraction/__init__.py
```

```python
# src/koshi/extraction/anzsco_occupations.py
import datetime as dt

from bs4 import BeautifulSoup

from koshi.models.occupations import Occupation
from koshi.provenance import require_provenance


def parse_anzsco_occupations(
    html: str, *, source_url: str, retrieved_at: dt.datetime
) -> list[Occupation]:
    require_provenance(reliability_tier="official_scraped", source_url=source_url)

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="occupation-list")
    rows = table.find("tbody").find_all("tr")

    occupations = []
    for row in rows:
        code, name, unit_group = (c.get_text(strip=True) for c in row.find_all("td"))
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
    return occupations
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extraction_anzsco.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/koshi/extraction/ tests/fixtures/anzsco_sample.html tests/test_extraction_anzsco.py
git commit -m "Add ANZSCO occupation-list parser (extraction tier 2)"
```

---

### Task 6: `eoi_rounds` table

**Files:**
- Create: `src/koshi/models/eoi_rounds.py`
- Create: `alembic/versions/0003_create_eoi_rounds.py`
- Test: `tests/test_eoi_rounds_model.py`

**Interfaces:**
- Consumes: `koshi.models.occupations.Occupation` (Task 4, FK target).
- Produces: `koshi.models.eoi_rounds.EoiRound` (columns: `id`, `visa_code`, `occupation_code` nullable, `round_date`, `threshold_points`, `invitations_issued` nullable, `source_url`, `retrieved_at`, `reliability_tier`) — Task 7's parser populates it, Task 9's momentum computation and Task 11's endpoint read it.

Note: `visa_code` is a plain string, not yet a foreign key to `visa_subclasses` — that table doesn't exist until the visa-comparison slice. Documented here rather than left as a silent inconsistency.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eoi_rounds_model.py
import datetime as dt

from koshi.models.eoi_rounds import EoiRound


def test_insert_and_read_eoi_round(db_session):
    from koshi.models.occupations import Occupation

    db_session.add(
        Occupation(
            code="261313", name="Software Engineer", unit_group="2613",
            source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()

    round_row = EoiRound(
        visa_code="189",
        occupation_code="261313",
        round_date=dt.date(2026, 7, 24),
        threshold_points=85,
        invitations_issued=120,
        source_url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
        retrieved_at=dt.datetime(2026, 7, 25, tzinfo=dt.timezone.utc),
        reliability_tier="official_scraped",
    )
    db_session.add(round_row)
    db_session.commit()

    found = db_session.query(EoiRound).filter_by(occupation_code="261313").one()
    assert found.threshold_points == 85
    assert found.visa_code == "189"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_eoi_rounds_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'koshi.models.eoi_rounds'`

- [ ] **Step 3: Write the model and migration**

```python
# src/koshi/models/eoi_rounds.py
import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class EoiRound(Base):
    __tablename__ = "eoi_rounds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    visa_code: Mapped[str] = mapped_column(String, nullable=False)
    occupation_code: Mapped[str | None] = mapped_column(
        String, ForeignKey("occupations.code"), nullable=True
    )
    round_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    threshold_points: Mapped[int] = mapped_column(Integer, nullable=False)
    invitations_issued: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_scraped")
```

```python
# alembic/versions/0003_create_eoi_rounds.py
"""create eoi_rounds

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-14
"""
import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eoi_rounds",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("visa_code", sa.String, nullable=False),
        sa.Column("occupation_code", sa.String, sa.ForeignKey("occupations.code"), nullable=True),
        sa.Column("round_date", sa.Date, nullable=False),
        sa.Column("threshold_points", sa.Integer, nullable=False),
        sa.Column("invitations_issued", sa.Integer, nullable=True),
        sa.Column("source_url", sa.String, nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String, nullable=False, server_default="official_scraped"),
    )


def downgrade() -> None:
    op.drop_table("eoi_rounds")
```

Add `import koshi.models.eoi_rounds  # noqa: F401` to `alembic/env.py`.

Run: `DATABASE_URL=postgresql+psycopg://koshi:koshi@localhost:5432/koshi alembic upgrade head`

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_eoi_rounds_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/koshi/models/eoi_rounds.py alembic/versions/0003_create_eoi_rounds.py alembic/env.py tests/test_eoi_rounds_model.py
git commit -m "Add eoi_rounds table"
```

---

### Task 7: SkillSelect round-results extraction parser

**Files:**
- Create: `src/koshi/extraction/skillselect_rounds.py`
- Create: `tests/fixtures/skillselect_rounds_sample.html`
- Test: `tests/test_extraction_skillselect.py`

**Interfaces:**
- Consumes: `koshi.models.eoi_rounds.EoiRound` (Task 6), `koshi.provenance.require_provenance` (Task 4).
- Produces: `koshi.extraction.skillselect_rounds.parse_skillselect_rounds(html: str, *, visa_code: str, source_url: str, retrieved_at: dt.datetime) -> list[EoiRound]`.

- [ ] **Step 1: Write the fixture and the failing test**

```html
<!-- tests/fixtures/skillselect_rounds_sample.html -->
<p>Round date: 24 July 2026</p>
<table id="round-results">
  <thead><tr><th>Occupation</th><th>Points Threshold</th><th>Invitations Issued</th></tr></thead>
  <tbody>
    <tr><td>261313</td><td>85</td><td>120</td></tr>
    <tr><td>254499</td><td>75</td><td>90</td></tr>
  </tbody>
</table>
```

```python
# tests/test_extraction_skillselect.py
import datetime as dt
from pathlib import Path

from koshi.extraction.skillselect_rounds import parse_skillselect_rounds

FIXTURE = (Path(__file__).parent / "fixtures" / "skillselect_rounds_sample.html").read_text()
SOURCE_URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"
RETRIEVED_AT = dt.datetime(2026, 7, 25, tzinfo=dt.timezone.utc)


def test_parses_round_date_and_two_rows():
    result = parse_skillselect_rounds(
        FIXTURE, visa_code="189", source_url=SOURCE_URL, retrieved_at=RETRIEVED_AT
    )

    assert len(result) == 2
    swe = next(r for r in result if r.occupation_code == "261313")
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

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extraction_skillselect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'koshi.extraction.skillselect_rounds'`

- [ ] **Step 3: Write the parser**

```python
# src/koshi/extraction/skillselect_rounds.py
import datetime as dt
import re

from bs4 import BeautifulSoup

from koshi.models.eoi_rounds import EoiRound
from koshi.provenance import require_provenance

ROUND_DATE_RE = re.compile(r"Round date:\s*(\d{1,2} \w+ \d{4})")


def parse_skillselect_rounds(
    html: str, *, visa_code: str, source_url: str, retrieved_at: dt.datetime
) -> list[EoiRound]:
    require_provenance(reliability_tier="official_scraped", source_url=source_url)

    soup = BeautifulSoup(html, "lxml")
    date_match = ROUND_DATE_RE.search(soup.get_text())
    if not date_match:
        raise ValueError("could not find round date in page")
    round_date = dt.datetime.strptime(date_match.group(1), "%d %B %Y").date()

    table = soup.find("table", id="round-results")
    rows = table.find("tbody").find_all("tr")

    results = []
    for row in rows:
        occupation_code, threshold, invitations = (
            c.get_text(strip=True) for c in row.find_all("td")
        )
        results.append(
            EoiRound(
                visa_code=visa_code,
                occupation_code=occupation_code,
                round_date=round_date,
                threshold_points=int(threshold),
                invitations_issued=int(invitations),
                source_url=source_url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extraction_skillselect.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/koshi/extraction/skillselect_rounds.py tests/fixtures/skillselect_rounds_sample.html tests/test_extraction_skillselect.py
git commit -m "Add SkillSelect round-results parser (extraction tier 2)"
```

---

### Task 8: `ceiling_usage` table + manual-curation seed loader

**Files:**
- Create: `src/koshi/models/ceiling_usage.py`
- Create: `alembic/versions/0004_create_ceiling_usage.py`
- Create: `src/koshi/seeds/__init__.py`
- Create: `src/koshi/seeds/loader.py`
- Create: `src/koshi/seeds/ceiling_usage_manual.yaml`
- Test: `tests/test_ceiling_usage_model.py`
- Test: `tests/test_ceiling_seed_loader.py`

**Interfaces:**
- Consumes: `koshi.provenance.require_provenance` (Task 4).
- Produces: `koshi.models.ceiling_usage.CeilingUsage` (columns: `id`, `occupation_code`, `program_year`, `issued`, `ceiling`, `as_of_date`, `source_url`, `retrieved_at`, `reliability_tier`) — Task 10's insight generator and Task 11's endpoint read it.
- Produces: `koshi.seeds.loader.load_ceiling_usage_seed(path: Path) -> list[CeilingUsage]`.

This is design spec §5 tier 5 (manual curation) in practice: the planning-levels page ceilings come from is a periodic PDF report, not a clean table (§4's honest note) — this task seeds real, cited numbers by hand rather than building a PDF parser that would be overkill for one slice.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ceiling_usage_model.py
import datetime as dt

from koshi.models.ceiling_usage import CeilingUsage


def test_insert_and_read_ceiling_usage(db_session):
    from koshi.models.occupations import Occupation

    db_session.add(
        Occupation(
            code="261313", name="Software Engineer", unit_group="2613",
            source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()

    row = CeilingUsage(
        occupation_code="261313",
        program_year="2025-26",
        issued=3200,
        ceiling=5000,
        as_of_date=dt.date(2026, 7, 31),
        source_url="https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels",
        retrieved_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
        reliability_tier="official_curated",
    )
    db_session.add(row)
    db_session.commit()

    found = db_session.query(CeilingUsage).filter_by(occupation_code="261313").one()
    assert found.issued == 3200
    assert found.ceiling == 5000
    assert found.reliability_tier == "official_curated"
```

```python
# tests/test_ceiling_seed_loader.py
import datetime as dt

import pytest

from koshi.provenance import ProvenanceError
from koshi.seeds.loader import load_ceiling_usage_seed

GOOD_YAML = """
- occupation_code: "261313"
  program_year: "2025-26"
  issued: 3200
  ceiling: 5000
  as_of_date: "2026-07-31"
  source_url: "https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels"
  retrieved_at: "2026-08-01T00:00:00+00:00"
"""

BAD_YAML = """
- occupation_code: "261313"
  program_year: "2025-26"
  issued: 3200
  ceiling: 5000
  as_of_date: "2026-07-31"
  source_url: ""
  retrieved_at: "2026-08-01T00:00:00+00:00"
"""


def test_loads_one_row_from_seed_file(tmp_path):
    seed_file = tmp_path / "seed.yaml"
    seed_file.write_text(GOOD_YAML)

    rows = load_ceiling_usage_seed(seed_file)

    assert len(rows) == 1
    assert rows[0].occupation_code == "261313"
    assert rows[0].issued == 3200
    assert rows[0].ceiling == 5000
    assert rows[0].as_of_date == dt.date(2026, 7, 31)
    assert rows[0].reliability_tier == "official_curated"


def test_rejects_row_missing_source_url(tmp_path):
    seed_file = tmp_path / "bad_seed.yaml"
    seed_file.write_text(BAD_YAML)

    with pytest.raises(ProvenanceError):
        load_ceiling_usage_seed(seed_file)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ceiling_usage_model.py tests/test_ceiling_seed_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'koshi.models.ceiling_usage'`

- [ ] **Step 3: Write the model, migration, and loader**

```python
# src/koshi/models/ceiling_usage.py
import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class CeilingUsage(Base):
    __tablename__ = "ceiling_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occupation_code: Mapped[str] = mapped_column(String, ForeignKey("occupations.code"), nullable=False)
    program_year: Mapped[str] = mapped_column(String, nullable=False)
    issued: Mapped[int] = mapped_column(Integer, nullable=False)
    ceiling: Mapped[int] = mapped_column(Integer, nullable=False)
    as_of_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="official_curated")
```

```python
# alembic/versions/0004_create_ceiling_usage.py
"""create ceiling_usage

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-14
"""
import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ceiling_usage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("occupation_code", sa.String, sa.ForeignKey("occupations.code"), nullable=False),
        sa.Column("program_year", sa.String, nullable=False),
        sa.Column("issued", sa.Integer, nullable=False),
        sa.Column("ceiling", sa.Integer, nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("source_url", sa.String, nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_tier", sa.String, nullable=False, server_default="official_curated"),
    )


def downgrade() -> None:
    op.drop_table("ceiling_usage")
```

Add `import koshi.models.ceiling_usage  # noqa: F401` to `alembic/env.py`.

Run: `DATABASE_URL=postgresql+psycopg://koshi:koshi@localhost:5432/koshi alembic upgrade head`

```python
# src/koshi/seeds/__init__.py
```

```python
# src/koshi/seeds/loader.py
import datetime as dt
from pathlib import Path

import yaml

from koshi.models.ceiling_usage import CeilingUsage
from koshi.provenance import require_provenance


def load_ceiling_usage_seed(path: Path) -> list[CeilingUsage]:
    entries = yaml.safe_load(path.read_text())
    rows = []
    for entry in entries:
        require_provenance(reliability_tier="official_curated", source_url=entry["source_url"])
        rows.append(
            CeilingUsage(
                occupation_code=entry["occupation_code"],
                program_year=entry["program_year"],
                issued=entry["issued"],
                ceiling=entry["ceiling"],
                as_of_date=dt.date.fromisoformat(entry["as_of_date"]),
                source_url=entry["source_url"],
                retrieved_at=dt.datetime.fromisoformat(entry["retrieved_at"]),
                reliability_tier="official_curated",
            )
        )
    return rows
```

```yaml
# src/koshi/seeds/ceiling_usage_manual.yaml
# Manually curated against the Migration Program planning levels report
# (design spec §4/§5 tier 5 — this page is a periodic PDF, not a scrapable
# table; values entered by hand and cited, reviewed on the cadence §11 sets).
- occupation_code: "261313"
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ceiling_usage_model.py tests/test_ceiling_seed_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/koshi/models/ceiling_usage.py alembic/versions/0004_create_ceiling_usage.py alembic/env.py src/koshi/seeds/ tests/test_ceiling_usage_model.py tests/test_ceiling_seed_loader.py
git commit -m "Add ceiling_usage table and manual-curation seed loader (extraction tier 5)"
```

---

### Task 9: `occupation_momentum` — derived, not scraped

**Files:**
- Create: `src/koshi/models/occupation_momentum.py`
- Create: `alembic/versions/0005_create_occupation_momentum.py`
- Create: `src/koshi/momentum.py`
- Test: `tests/test_momentum.py`

**Interfaces:**
- Consumes: `koshi.models.eoi_rounds.EoiRound` (Task 6).
- Produces: `koshi.models.occupation_momentum.OccupationMomentum` (columns: `id`, `occupation_code`, `computed_at`, `direction`, `reliability_tier` fixed `"derived"`, no `source_url`). Produces `koshi.momentum.compute_momentum(session, occupation_code) -> str | None` and `koshi.momentum.refresh_momentum(session, occupation_code) -> None` — Task 11's endpoint reads the table this writes.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_momentum.py
import datetime as dt

from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupation_momentum import OccupationMomentum
from koshi.models.occupations import Occupation
from koshi.momentum import compute_momentum, refresh_momentum


def _seed_occupation(db_session, code="261313"):
    db_session.add(
        Occupation(
            code=code, name="Software Engineer", unit_group="2613",
            source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()


def _seed_rounds(db_session, code, thresholds):
    base_date = dt.date(2026, 5, 1)
    for i, points in enumerate(thresholds):
        db_session.add(
            EoiRound(
                visa_code="189",
                occupation_code=code,
                round_date=base_date + dt.timedelta(days=30 * i),
                threshold_points=points,
                invitations_issued=100,
                source_url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
                retrieved_at=dt.datetime.now(dt.timezone.utc),
                reliability_tier="official_scraped",
            )
        )
    db_session.commit()


def test_compute_momentum_rising_when_threshold_increases(db_session):
    _seed_occupation(db_session)
    _seed_rounds(db_session, "261313", thresholds=[70, 75, 85])  # oldest -> newest

    assert compute_momentum(db_session, "261313") == "rising"


def test_compute_momentum_falling_when_threshold_decreases(db_session):
    _seed_occupation(db_session)
    _seed_rounds(db_session, "261313", thresholds=[85, 80, 70])

    assert compute_momentum(db_session, "261313") == "falling"


def test_compute_momentum_none_with_fewer_than_three_rounds(db_session):
    _seed_occupation(db_session)
    _seed_rounds(db_session, "261313", thresholds=[70, 75])

    assert compute_momentum(db_session, "261313") is None


def test_refresh_momentum_persists_a_derived_row(db_session):
    _seed_occupation(db_session)
    _seed_rounds(db_session, "261313", thresholds=[70, 75, 85])

    refresh_momentum(db_session, "261313")

    row = db_session.query(OccupationMomentum).filter_by(occupation_code="261313").one()
    assert row.direction == "rising"
    assert row.reliability_tier == "derived"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_momentum.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'koshi.models.occupation_momentum'`

- [ ] **Step 3: Write the model, migration, and computation**

```python
# src/koshi/models/occupation_momentum.py
import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from koshi.db import Base


class OccupationMomentum(Base):
    __tablename__ = "occupation_momentum"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occupation_code: Mapped[str] = mapped_column(String, ForeignKey("occupations.code"), nullable=False)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)  # rising | falling | steady
    reliability_tier: Mapped[str] = mapped_column(String, nullable=False, default="derived")
```

```python
# alembic/versions/0005_create_occupation_momentum.py
"""create occupation_momentum

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-14
"""
import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "occupation_momentum",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("occupation_code", sa.String, sa.ForeignKey("occupations.code"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String, nullable=False),
        sa.Column("reliability_tier", sa.String, nullable=False, server_default="derived"),
    )


def downgrade() -> None:
    op.drop_table("occupation_momentum")
```

Add `import koshi.models.occupation_momentum  # noqa: F401` to `alembic/env.py`.

Run: `DATABASE_URL=postgresql+psycopg://koshi:koshi@localhost:5432/koshi alembic upgrade head`

```python
# src/koshi/momentum.py
import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupation_momentum import OccupationMomentum


def compute_momentum(session: Session, occupation_code: str) -> str | None:
    """Trailing 3-round threshold delta. Computed from koshi's own
    eoi_rounds rows — never scraped (design spec §3.3)."""
    rounds = session.scalars(
        select(EoiRound)
        .where(EoiRound.occupation_code == occupation_code)
        .order_by(EoiRound.round_date.desc())
        .limit(3)
    ).all()
    if len(rounds) < 3:
        return None

    newest, _mid, oldest = rounds
    delta = newest.threshold_points - oldest.threshold_points
    if delta > 0:
        return "rising"
    if delta < 0:
        return "falling"
    return "steady"


def refresh_momentum(session: Session, occupation_code: str) -> None:
    direction = compute_momentum(session, occupation_code)
    if direction is None:
        return
    session.add(
        OccupationMomentum(
            occupation_code=occupation_code,
            computed_at=dt.datetime.now(dt.timezone.utc),
            direction=direction,
            reliability_tier="derived",
        )
    )
    session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_momentum.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/koshi/models/occupation_momentum.py alembic/versions/0005_create_occupation_momentum.py alembic/env.py src/koshi/momentum.py tests/test_momentum.py
git commit -m "Add occupation_momentum (derived) and its computation"
```

---

### Task 10: Deterministic insight generation + phrase-ban test

**Files:**
- Create: `src/koshi/insights.py`
- Test: `tests/test_insights.py`

**Interfaces:**
- Produces: `koshi.insights.generate_ceiling_insight(*, issued: int, ceiling: int, direction: str) -> str` — Task 11's endpoint calls this.

This is the design spec §7 enforcement point: "what this means" text is a template keyed to data conditions, never an LLM call, and the phrase-ban test is what actually checks that, not just prose asserting it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_insights.py
from koshi.insights import generate_ceiling_insight

BANNED_PHRASES = [
    "you should",
    "you can",
    "you're eligible",
    "you are eligible",
    "you qualify",
    "you will",
]


def test_ceiling_insight_never_uses_advice_language():
    for direction in ("rising", "falling", "steady"):
        text = generate_ceiling_insight(issued=3200, ceiling=5000, direction=direction)
        lowered = text.lower()
        for phrase in BANNED_PHRASES:
            assert phrase not in lowered, f"banned phrase {phrase!r} found in: {text!r}"


def test_ceiling_insight_reports_correct_numbers():
    text = generate_ceiling_insight(issued=3200, ceiling=5000, direction="falling")
    assert "3200" in text
    assert "5000" in text
    assert "1800" in text  # places left = ceiling - issued
    assert "falling" in text.lower()


def test_ceiling_insight_reports_percent_used():
    text = generate_ceiling_insight(issued=2500, ceiling=5000, direction="steady")
    assert "50%" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_insights.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'koshi.insights'`

- [ ] **Step 3: Write the templates**

```python
# src/koshi/insights.py
_PACE_PHRASES = {
    "rising": "the points threshold has been rising over the last three rounds",
    "falling": "the points threshold has been falling over the last three rounds",
    "steady": "the points threshold has stayed steady over the last three rounds",
}


def generate_ceiling_insight(*, issued: int, ceiling: int, direction: str) -> str:
    """Deterministic template, keyed to the data — never an LLM call
    (design spec §7). No scoring, ranking, or personalized prediction."""
    places_left = ceiling - issued
    pct_used = round(issued / ceiling * 100)
    pace_phrase = _PACE_PHRASES.get(direction, _PACE_PHRASES["steady"])

    return (
        f"{pct_used}% of this occupation's ceiling has been issued this program year "
        f"({issued} of {ceiling}), leaving {places_left} places. "
        f"{pace_phrase.capitalize()}."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_insights.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/koshi/insights.py tests/test_insights.py
git commit -m "Add deterministic ceiling insight template with phrase-ban test"
```

---

### Task 11: `GET /v1/occupations/{code}`

**Files:**
- Create: `src/koshi/schemas/__init__.py`
- Create: `src/koshi/schemas/occupation.py`
- Create: `src/koshi/api/__init__.py`
- Create: `src/koshi/api/occupations.py`
- Modify: `src/koshi/main.py` — register the router
- Test: `tests/test_api_occupation_detail.py`

**Interfaces:**
- Consumes: `koshi.models.occupations.Occupation`, `koshi.models.ceiling_usage.CeilingUsage`, `koshi.models.eoi_rounds.EoiRound`, `koshi.models.occupation_momentum.OccupationMomentum`, `koshi.insights.generate_ceiling_insight`, `koshi.db.get_session`.
- Produces: `koshi.schemas.occupation.SourcedFact`, `koshi.schemas.occupation.OccupationProfile` — reused by any future endpoint that needs the same "value + provenance" shape.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_occupation_detail.py
import datetime as dt

from fastapi.testclient import TestClient

from koshi.db import get_session
from koshi.main import app
from koshi.models.ceiling_usage import CeilingUsage
from koshi.models.occupations import Occupation


def _seed(db_session):
    db_session.add(
        Occupation(
            code="261313", name="Software Engineer", unit_group="2613",
            source_url="https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco",
            retrieved_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
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


def test_get_occupation_returns_profile_with_provenance(db_session):
    _seed(db_session)
    app.dependency_overrides[get_session] = lambda: db_session
    client = TestClient(app)

    response = client.get("/v1/occupations/261313")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "261313"
    assert body["places_left"] == 1800
    assert body["ceiling_issued"]["reliability_tier"] == "official_curated"
    assert body["ceiling_issued"]["source_url"].startswith("https://immi.homeaffairs.gov.au")
    assert "1800" in body["insight"]
    assert body["momentum"] is None  # fewer than 3 eoi_rounds seeded

    app.dependency_overrides.clear()


def test_get_occupation_404_for_unknown_code(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    client = TestClient(app)

    response = client.get("/v1/occupations/999999")

    assert response.status_code == 404
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_occupation_detail.py -v`
Expected: FAIL — `404` for the first test (no route registered yet) instead of the asserted `200`

- [ ] **Step 3: Write the schema and endpoint**

```python
# src/koshi/schemas/__init__.py
```

```python
# src/koshi/schemas/occupation.py
import datetime as dt

from pydantic import BaseModel


class SourcedFact(BaseModel):
    value: int
    reliability_tier: str
    retrieved_at: dt.datetime
    source_url: str


class OccupationProfile(BaseModel):
    code: str
    name: str
    unit_group: str
    ceiling_issued: SourcedFact
    ceiling_cap: SourcedFact
    places_left: int
    latest_threshold: SourcedFact | None
    momentum: str | None
    insight: str


class OccupationListItem(BaseModel):
    code: str
    name: str
    momentum: str | None
```

```python
# src/koshi/api/__init__.py
```

```python
# src/koshi/api/occupations.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.db import get_session
from koshi.insights import generate_ceiling_insight
from koshi.models.ceiling_usage import CeilingUsage
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupation_momentum import OccupationMomentum
from koshi.models.occupations import Occupation
from koshi.schemas.occupation import OccupationProfile, SourcedFact

router = APIRouter(prefix="/v1/occupations", tags=["occupations"])


@router.get("/{code}", response_model=OccupationProfile)
def get_occupation(code: str, session: Session = Depends(get_session)) -> OccupationProfile:
    occupation = session.get(Occupation, code)
    if occupation is None:
        raise HTTPException(status_code=404, detail=f"unknown occupation code {code!r}")

    latest_ceiling = session.scalar(
        select(CeilingUsage).where(CeilingUsage.occupation_code == code).order_by(CeilingUsage.as_of_date.desc())
    )
    if latest_ceiling is None:
        raise HTTPException(status_code=404, detail=f"no ceiling data for {code!r} yet")

    latest_round = session.scalar(
        select(EoiRound).where(EoiRound.occupation_code == code).order_by(EoiRound.round_date.desc())
    )
    latest_momentum = session.scalar(
        select(OccupationMomentum)
        .where(OccupationMomentum.occupation_code == code)
        .order_by(OccupationMomentum.computed_at.desc())
    )

    insight = generate_ceiling_insight(
        issued=latest_ceiling.issued,
        ceiling=latest_ceiling.ceiling,
        direction=latest_momentum.direction if latest_momentum else "steady",
    )

    return OccupationProfile(
        code=occupation.code,
        name=occupation.name,
        unit_group=occupation.unit_group,
        ceiling_issued=SourcedFact(
            value=latest_ceiling.issued,
            reliability_tier=latest_ceiling.reliability_tier,
            retrieved_at=latest_ceiling.retrieved_at,
            source_url=latest_ceiling.source_url,
        ),
        ceiling_cap=SourcedFact(
            value=latest_ceiling.ceiling,
            reliability_tier=latest_ceiling.reliability_tier,
            retrieved_at=latest_ceiling.retrieved_at,
            source_url=latest_ceiling.source_url,
        ),
        places_left=latest_ceiling.ceiling - latest_ceiling.issued,
        latest_threshold=(
            SourcedFact(
                value=latest_round.threshold_points,
                reliability_tier=latest_round.reliability_tier,
                retrieved_at=latest_round.retrieved_at,
                source_url=latest_round.source_url,
            )
            if latest_round
            else None
        ),
        momentum=latest_momentum.direction if latest_momentum else None,
        insight=insight,
    )
```

```python
# src/koshi/main.py  (modify — add the import and include_router call)
from fastapi import FastAPI

from koshi.api.occupations import router as occupations_router

app = FastAPI(title="koshi", version="0.1.0", openapi_url="/v1/openapi.json", docs_url="/v1/docs")
app.include_router(occupations_router)


@app.get("/v1/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_occupation_detail.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/koshi/schemas/ src/koshi/api/ src/koshi/main.py tests/test_api_occupation_detail.py
git commit -m "Add GET /v1/occupations/{code} with provenance on every fact"
```

---

### Task 12: `GET /v1/occupations` — list, sortable by momentum

**Files:**
- Modify: `src/koshi/api/occupations.py` — add the list route
- Test: `tests/test_api_occupation_list.py`

**Interfaces:**
- Consumes: `koshi.schemas.occupation.OccupationListItem` (Task 11), `koshi.models.occupations.Occupation`, `koshi.models.occupation_momentum.OccupationMomentum`.
- Produces: nothing further — this is the last endpoint in this slice.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_occupation_list.py
import datetime as dt

from fastapi.testclient import TestClient

from koshi.db import get_session
from koshi.main import app
from koshi.models.occupation_momentum import OccupationMomentum
from koshi.models.occupations import Occupation


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


def test_list_occupations_sortable_by_momentum(db_session):
    _seed_two_occupations_with_momentum(db_session)
    app.dependency_overrides[get_session] = lambda: db_session
    client = TestClient(app)

    response = client.get("/v1/occupations?sort=momentum")

    assert response.status_code == 200
    codes_in_order = [item["code"] for item in response.json()]
    assert codes_in_order == ["261313", "254499"]  # rising ranks before falling

    app.dependency_overrides.clear()


def test_list_occupations_defaults_to_code_order(db_session):
    _seed_two_occupations_with_momentum(db_session)
    app.dependency_overrides[get_session] = lambda: db_session
    client = TestClient(app)

    response = client.get("/v1/occupations")

    codes_in_order = [item["code"] for item in response.json()]
    assert codes_in_order == ["254499", "261313"]  # lexical code order

    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_occupation_list.py -v`
Expected: FAIL — `404 Not Found` (no `GET /v1/occupations` route yet)

- [ ] **Step 3: Add the list route**

```python
# src/koshi/api/occupations.py  (add — keep the existing /{code} route above/below this)
from koshi.schemas.occupation import OccupationListItem  # add to the existing import line

_MOMENTUM_SORT_ORDER = {"rising": 0, "steady": 1, "falling": 2, None: 3}


@router.get("", response_model=list[OccupationListItem])
def list_occupations(
    sort: str = "code", session: Session = Depends(get_session)
) -> list[OccupationListItem]:
    occupations = session.scalars(select(Occupation).order_by(Occupation.code)).all()

    items = []
    for occupation in occupations:
        latest_momentum = session.scalar(
            select(OccupationMomentum)
            .where(OccupationMomentum.occupation_code == occupation.code)
            .order_by(OccupationMomentum.computed_at.desc())
        )
        items.append(
            OccupationListItem(
                code=occupation.code,
                name=occupation.name,
                momentum=latest_momentum.direction if latest_momentum else None,
            )
        )

    if sort == "momentum":
        items.sort(key=lambda item: _MOMENTUM_SORT_ORDER.get(item.momentum, 3))
    return items
```

This route's `@router.get("", ...)` decorator must appear **above** the existing `@router.get("/{code}", ...)` decorator in the file — FastAPI matches routes in registration order, and `/{code}` would otherwise capture requests to the bare `/v1/occupations` path first. Cut the existing `get_occupation` function, paste this new `list_occupations` function in its place at the top, then paste `get_occupation` back in immediately after it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_occupation_list.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/koshi/api/occupations.py tests/test_api_occupation_list.py
git commit -m "Add GET /v1/occupations list endpoint, sortable by momentum"
```

---

### Task 13: Pipeline — wire crawl and parse together

Tasks 3, 5, and 7 built and tested the crawler and both parsers in
isolation. Nothing so far actually calls them together — without this task,
"koshi's crawler feeds its parsers" is only true in the design spec, not in
the code. This task closes that gap for the two live-scraped tables
(`ceiling_usage` stays manually curated per Task 8 — nothing to wire there).

**Files:**
- Create: `src/koshi/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `koshi.crawler.fetch.fetch_and_register` (Task 3, now returning content), `koshi.extraction.anzsco_occupations.parse_anzsco_occupations` (Task 5), `koshi.extraction.skillselect_rounds.parse_skillselect_rounds` (Task 7).
- Produces: `koshi.pipeline.sync_anzsco_occupations(session, *, url=ANZSCO_URL, client=None) -> list[Occupation]`, `koshi.pipeline.sync_skillselect_rounds(session, *, url=SKILLSELECT_ROUNDS_URL, visa_code="189", client=None) -> list[EoiRound]`. A future Cloud Run Job (out of scope — design spec §11) calls these on a schedule; for now they're called manually or from a script.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'koshi.pipeline'`

- [ ] **Step 3: Write the pipeline module**

```python
# src/koshi/pipeline.py
import datetime as dt

import httpx
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.anzsco_occupations import parse_anzsco_occupations
from koshi.extraction.skillselect_rounds import parse_skillselect_rounds
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupations import Occupation

ANZSCO_URL = "https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco"
SKILLSELECT_ROUNDS_URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"


def sync_anzsco_occupations(
    session: Session, *, url: str = ANZSCO_URL, client: httpx.Client | None = None
) -> list[Occupation]:
    _page, changed, content = fetch_and_register(
        session, url=url, domain="www.jobsandskills.gov.au", category="anzsco_occupations", client=client
    )
    if not changed:
        return []

    occupations = parse_anzsco_occupations(
        content.decode("utf-8"), source_url=url, retrieved_at=dt.datetime.now(dt.timezone.utc)
    )
    for occupation in occupations:
        session.merge(occupation)
    session.commit()
    return occupations


def sync_skillselect_rounds(
    session: Session,
    *,
    url: str = SKILLSELECT_ROUNDS_URL,
    visa_code: str = "189",
    client: httpx.Client | None = None,
) -> list[EoiRound]:
    _page, changed, content = fetch_and_register(
        session, url=url, domain="immi.homeaffairs.gov.au", category="skillselect_rounds", client=client
    )
    if not changed:
        return []

    rounds = parse_skillselect_rounds(
        content.decode("utf-8"),
        visa_code=visa_code,
        source_url=url,
        retrieved_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add_all(rounds)
    session.commit()
    return rounds
```

`session.merge` (not `add`) for occupations specifically: ANZSCO codes are near-static but not immutable (design spec §4's freshness table), so a re-run with an updated name for an existing code should update the row, not raise a primary-key conflict. `eoi_rounds` uses `add_all` because every round is a genuinely new row — there's no natural key to merge on.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/koshi/pipeline.py tests/test_pipeline.py
git commit -m "Wire crawler and parsers together: sync_anzsco_occupations, sync_skillselect_rounds"
```

---

### Task 14: OpenAPI contract check + local-dev README

**Files:**
- Test: `tests/test_openapi_contract.py`
- Modify: `README.md` — add a "Local development" section

**Interfaces:**
- Consumes: `koshi.main.app` (Task 1, now with both routers registered).
- Produces: nothing further — this closes out the slice.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_openapi_contract.py
from fastapi.testclient import TestClient

from koshi.main import app


def test_openapi_schema_lists_this_slices_paths():
    client = TestClient(app)
    response = client.get("/v1/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "/v1/occupations/{code}" in schema["paths"]
    assert "/v1/occupations" in schema["paths"]
    assert "/v1/healthz" in schema["paths"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_openapi_contract.py -v`
Expected: FAIL if any path is missing — confirms which router registration was missed, if any

- [ ] **Step 3: Fix registration if needed, then document local dev**

If the test fails, check `src/koshi/main.py` includes `app.include_router(occupations_router)` (Task 11). If it already passes, no code change is needed here — only the README update below.

Add to `README.md`:

```markdown
## Local development

1. `docker compose up -d postgres`
2. `docker compose exec postgres createdb -U koshi koshi_test` (first time only)
3. `pip install -e ".[dev]"`
4. `DATABASE_URL=postgresql+psycopg://koshi:koshi@localhost:5432/koshi alembic upgrade head`
5. `pytest` — runs against `koshi_test` (see `tests/conftest.py`)
6. `uvicorn koshi.main:app --reload` — serves the API at `http://localhost:8000/v1`, docs at `/v1/docs`

No Cloud SQL, no Terraform, no Cloud Run needed for local development — see
the design spec §9/§11 for why that's deliberate, not a shortcut.
```

- [ ] **Step 4: Run the full test suite**

Run: `pytest -v`
Expected: PASS — every test from Tasks 1–13

- [ ] **Step 5: Commit**

```bash
git add tests/test_openapi_contract.py README.md
git commit -m "Add OpenAPI contract test and local-dev instructions; close out occupation slice v2"
```
