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


def fetch_bytes(
    url: str, *, domain: str, category: str, client: httpx.Client | None = None
) -> bytes:
    """Fetch a binary resource (e.g. an .xlsx workbook).

    Retries and error semantics match fetch_and_register.
    """
    owns_client = client is None
    active_client = client or httpx.Client(
        # Workbooks are larger than pages; the read budget reflects that.
        timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0),
        follow_redirects=True,
    )
    try:
        try:
            return _get_with_retry(active_client, url).content
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            raise FetchError(url=url, domain=domain, category=category, cause=exc) from exc
    finally:
        if owns_client:
            active_client.close()


def fetch_text(
    url: str, *, domain: str, category: str, client: httpx.Client | None = None
) -> str:
    """Fetch a page and return its text, without touching source_pages.

    For additional pages of a paginated source whose watermark is already
    tracked against page 1: registering all 103 ANZSCO listing pages as
    separate source_pages rows would bloat the registry without adding
    signal, since they change together.

    Retries and error semantics match fetch_and_register.
    """
    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=10.0)
    )
    try:
        try:
            return _get_with_retry(active_client, url).text
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            raise FetchError(url=url, domain=domain, category=category, cause=exc) from exc
    finally:
        if owns_client:
            active_client.close()


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
