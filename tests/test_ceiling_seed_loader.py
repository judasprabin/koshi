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
