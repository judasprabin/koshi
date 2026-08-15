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
