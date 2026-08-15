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
