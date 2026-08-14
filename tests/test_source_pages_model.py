from koshi.models.source_pages import SourcePage


def test_insert_and_read_source_page(db_session):
    page = SourcePage(
        url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
        domain="immi.homeaffairs.gov.au",
        category="skillselect_rounds",
        content_hash="abc123",
        status="active",
    )
    db_session.add(page)
    db_session.commit()

    found = db_session.query(SourcePage).filter_by(url=page.url).one()
    assert found.domain == "immi.homeaffairs.gov.au"
    assert found.status == "active"
