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
