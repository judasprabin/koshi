import datetime as dt

from koshi.models.ceiling_usage import CeilingUsage
from koshi.models.occupations import Occupation
from koshi.seeds.loader import load_ceiling_usage_seed, seed_ceiling_usage

GOOD_YAML = """
- occupation_code: "261313"
  program_year: "2025-26"
  issued: 3200
  ceiling: 5000
  as_of_date: "2026-07-31"
  source_url: "https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels"
  retrieved_at: "2026-08-01T00:00:00+00:00"
"""

# issued > ceiling: "104% used, leaving -200 places" is nonsensical and
# must be rejected before it ever reaches the DB or generate_ceiling_insight.
ISSUED_EXCEEDS_CEILING_YAML = """
- occupation_code: "261313"
  program_year: "2025-26"
  issued: 5200
  ceiling: 5000
  as_of_date: "2026-07-31"
  source_url: "https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels"
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


def test_skips_row_where_issued_exceeds_ceiling_but_loads_other_valid_rows(tmp_path):
    seed_file = tmp_path / "issued_exceeds_ceiling.yaml"
    seed_file.write_text(
        ISSUED_EXCEEDS_CEILING_YAML
        + """- occupation_code: "254499"
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


def _seed_occupation(db_session, code="261313"):
    db_session.add(
        Occupation(
            code=code, name="Software Engineer", unit_group="2613",
            source_url="https://example.gov.au", retrieved_at=dt.datetime.now(dt.timezone.utc),
            reliability_tier="official_scraped",
        )
    )
    db_session.commit()


def test_seed_ceiling_usage_persists_rows(db_session, tmp_path):
    _seed_occupation(db_session)
    seed_file = tmp_path / "seed.yaml"
    seed_file.write_text(GOOD_YAML)

    new_rows = seed_ceiling_usage(db_session, seed_file)

    assert len(new_rows) == 1
    row = db_session.query(CeilingUsage).filter_by(occupation_code="261313").one()
    assert row.issued == 3200
    assert row.ceiling == 5000


def test_seed_ceiling_usage_is_idempotent_on_rerun(db_session, tmp_path):
    _seed_occupation(db_session)
    seed_file = tmp_path / "seed.yaml"
    seed_file.write_text(GOOD_YAML)

    first_run = seed_ceiling_usage(db_session, seed_file)
    second_run = seed_ceiling_usage(db_session, seed_file)

    assert len(first_run) == 1
    assert second_run == []  # already seeded (occupation_code, program_year, as_of_date) — no duplicate
    assert db_session.query(CeilingUsage).filter_by(occupation_code="261313").count() == 1


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
