import httpx
import pytest

from koshi.crawler.fetch import FetchError, fetch_and_register, hash_content

URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"


def _client_returning(body: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_new_page_is_registered_as_changed(db_session):
    body = b"<html>version one</html>"
    page, changed, text = fetch_and_register(
        db_session,
        url=URL,
        domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds",
        client=_client_returning(body),
    )
    assert changed is True
    assert page.content_hash == hash_content(body)
    assert text == body.decode("utf-8")


def test_unchanged_page_is_not_flagged_changed(db_session):
    body = b"<html>version one</html>"
    fetch_and_register(
        db_session, url=URL, domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds", client=_client_returning(body),
    )

    page, changed, text = fetch_and_register(
        db_session, url=URL, domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds", client=_client_returning(body),
    )
    assert changed is False


def test_changed_page_is_flagged_changed(db_session):
    fetch_and_register(
        db_session, url=URL, domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds", client=_client_returning(b"<html>version one</html>"),
    )

    page, changed, text = fetch_and_register(
        db_session, url=URL, domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds", client=_client_returning(b"<html>version TWO</html>"),
    )
    assert changed is True
    assert page.content_hash == hash_content(b"<html>version TWO</html>")
    assert text == b"<html>version TWO</html>".decode("utf-8")


def test_fetch_and_register_retries_transient_failures_then_succeeds(db_session, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)  # keep the test fast
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503, content=b"unavailable")
        return httpx.Response(200, content=b"<html>ok</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    page, changed, text = fetch_and_register(
        db_session,
        url="https://immi.homeaffairs.gov.au/retry-test",
        domain="immi.homeaffairs.gov.au",
        category="test",
        client=client,
    )

    assert attempts["count"] == 3
    assert changed is True
    assert text == "<html>ok</html>"


def test_fetch_and_register_raises_fetch_error_after_exhausting_retries(db_session, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"unavailable")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(FetchError):
        fetch_and_register(
            db_session,
            url="https://immi.homeaffairs.gov.au/always-503",
            domain="immi.homeaffairs.gov.au",
            category="test",
            client=client,
        )


def test_fetch_and_register_does_not_retry_a_404(db_session):
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404, content=b"not found")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(FetchError):
        fetch_and_register(
            db_session,
            url="https://immi.homeaffairs.gov.au/missing",
            domain="immi.homeaffairs.gov.au",
            category="test",
            client=client,
        )

    assert attempts["count"] == 1
