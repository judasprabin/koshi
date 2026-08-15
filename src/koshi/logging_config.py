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
