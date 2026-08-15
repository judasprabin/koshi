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
