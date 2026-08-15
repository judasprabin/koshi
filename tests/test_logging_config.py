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
