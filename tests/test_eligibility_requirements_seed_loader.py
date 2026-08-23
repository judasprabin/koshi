from koshi.models.eligibility_requirements import EligibilityRequirement
from koshi.seeds.loader import load_eligibility_requirements_seed, seed_eligibility_requirements

GOOD_YAML = """
- requirement_type: health
  summary: "Free from disease or condition threatening public health."
  source_url: "https://immi.homeaffairs.gov.au/help-support/meeting-our-requirements/health"
  retrieved_at: "2026-08-23T00:00:00+00:00"
"""


def test_loads_one_row_from_seed_file(tmp_path):
    seed_file = tmp_path / "seed.yaml"
    seed_file.write_text(GOOD_YAML)

    rows = load_eligibility_requirements_seed(seed_file)

    assert len(rows) == 1
    assert rows[0].requirement_type == "health"
    assert rows[0].reliability_tier == "official_curated"


def test_rejects_an_unrecognized_requirement_type(tmp_path):
    """Mirrors the DB CHECK constraint — a curation typo must be caught
    here, not surface as a constraint violation mid-commit."""
    seed_file = tmp_path / "seed.yaml"
    seed_file.write_text(
        """
- requirement_type: healthcare
  summary: "Typo'd requirement_type."
  source_url: "https://immi.homeaffairs.gov.au/help-support/meeting-our-requirements/health"
  retrieved_at: "2026-08-23T00:00:00+00:00"
- requirement_type: character
  summary: "Real entry."
  source_url: "https://immi.homeaffairs.gov.au/help-support/meeting-our-requirements/character"
  retrieved_at: "2026-08-23T00:00:00+00:00"
"""
    )

    rows = load_eligibility_requirements_seed(seed_file)

    assert len(rows) == 1
    assert rows[0].requirement_type == "character"


def test_empty_seed_file_loads_as_zero_rows_without_raising(tmp_path):
    seed_file = tmp_path / "empty.yaml"
    seed_file.write_text("# nothing to see here\n")

    rows = load_eligibility_requirements_seed(seed_file)

    assert rows == []


def test_seed_eligibility_requirements_persists_rows(db_session, tmp_path):
    seed_file = tmp_path / "seed.yaml"
    seed_file.write_text(GOOD_YAML)

    new_rows = seed_eligibility_requirements(db_session, seed_file)

    assert len(new_rows) == 1
    row = db_session.query(EligibilityRequirement).filter_by(requirement_type="health").one()
    assert "public health" in row.summary


def test_seed_eligibility_requirements_is_idempotent_on_rerun(db_session, tmp_path):
    seed_file = tmp_path / "seed.yaml"
    seed_file.write_text(GOOD_YAML)

    first_run = seed_eligibility_requirements(db_session, seed_file)
    second_run = seed_eligibility_requirements(db_session, seed_file)

    assert len(first_run) == 1
    assert second_run == []
    assert db_session.query(EligibilityRequirement).filter_by(requirement_type="health").count() == 1


def test_seed_eligibility_requirements_updates_summary_on_change(db_session, tmp_path):
    """A curated summary can be revised (e.g. after a policy change) —
    re-running the seed with updated prose must update the existing row,
    not silently keep the stale text."""
    seed_file = tmp_path / "seed.yaml"
    seed_file.write_text(GOOD_YAML)
    seed_eligibility_requirements(db_session, seed_file)

    seed_file.write_text(GOOD_YAML.replace(
        "Free from disease or condition threatening public health.",
        "Updated: free from disease or condition threatening public health.",
    ))
    updated = seed_eligibility_requirements(db_session, seed_file)

    assert len(updated) == 1
    row = db_session.query(EligibilityRequirement).filter_by(requirement_type="health").one()
    assert row.summary.startswith("Updated:")
    assert db_session.query(EligibilityRequirement).count() == 1
