import httpx

from koshi.crawler.fetch import fetch_and_register, hash_content

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
