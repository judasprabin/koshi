import datetime as dt

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_and_register
from koshi.extraction.anzsco_occupations import parse_anzsco_occupations
from koshi.extraction.skillselect_rounds import parse_skillselect_rounds
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupations import Occupation

ANZSCO_URL = "https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco"
SKILLSELECT_ROUNDS_URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"


def sync_anzsco_occupations(
    session: Session, *, url: str = ANZSCO_URL, client: httpx.Client | None = None
) -> list[Occupation]:
    _page, changed, content = fetch_and_register(
        session, url=url, domain="www.jobsandskills.gov.au", category="anzsco_occupations", client=client
    )
    if not changed:
        return []

    occupations = parse_anzsco_occupations(
        content.decode("utf-8"), source_url=url, retrieved_at=dt.datetime.now(dt.timezone.utc)
    )
    for occupation in occupations:
        session.merge(occupation)
    session.commit()
    return occupations


def sync_skillselect_rounds(
    session: Session,
    *,
    url: str = SKILLSELECT_ROUNDS_URL,
    visa_code: str = "189",
    client: httpx.Client | None = None,
) -> list[EoiRound]:
    _page, changed, content = fetch_and_register(
        session, url=url, domain="immi.homeaffairs.gov.au", category="skillselect_rounds", client=client
    )
    if not changed:
        return []

    rounds = parse_skillselect_rounds(
        content.decode("utf-8"),
        visa_code=visa_code,
        source_url=url,
        retrieved_at=dt.datetime.now(dt.timezone.utc),
    )

    # Upsert by (visa_code, occupation_code, round_date): a whole-page hash
    # change (build stamp, "last reviewed" date) re-parses the same round
    # data and must not manufacture duplicate rows / fake momentum.
    new_rounds = []
    for round_ in rounds:
        existing = session.scalar(
            select(EoiRound).where(
                EoiRound.visa_code == round_.visa_code,
                EoiRound.occupation_code == round_.occupation_code,
                EoiRound.round_date == round_.round_date,
            )
        )
        if existing is not None:
            continue
        session.add(round_)
        new_rounds.append(round_)
    session.commit()
    return new_rounds
