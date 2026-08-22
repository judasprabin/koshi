import datetime as dt
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.crawler.fetch import fetch_bytes, fetch_text
from koshi.crosswalk import normalize_title
from koshi.extraction.abs_anzsco import parse_abs_titles
from koshi.extraction.lin19051 import parse_lin_titles
from koshi.models.occupation_titles import OccupationTitle
from koshi.models.occupations import Occupation
from koshi.sources import ABS_ANZSCO, LIN19051

logger = logging.getLogger(__name__)


def sync_occupation_titles(
    session: Session,
    *,
    lin_url: str = LIN19051.url,
    abs_url: str = ABS_ANZSCO.url,
    client: httpx.Client | None = None,
) -> list[OccupationTitle]:
    """Load the name->code crosswalk from both sources.

    Upserts by (title_normalized, title_source), so re-running replaces a
    source's mapping in place rather than accumulating duplicates.

    Both sources are loaded because neither is sufficient: against a live
    invitation round, each resolves 132/140 on its own and their union
    resolves 140/140.
    """
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    staged: dict[tuple[str, str], OccupationTitle] = {}

    lin_html = fetch_text(
        lin_url, domain="www.legislation.gov.au", category="lin19051", client=client
    )
    for row in parse_lin_titles(lin_html).rows:
        key = (normalize_title(row.title), "LIN_19_051")
        staged.setdefault(key, OccupationTitle(
            title=row.title, title_normalized=key[0],
            occupation_code=row.occupation_code, title_source="LIN_19_051",
            anzsco_edition=row.anzsco_edition, source_url=lin_url,
            retrieved_at=retrieved_at, reliability_tier="official_scraped",
        ))

    abs_bytes = fetch_bytes(
        abs_url, domain="www.abs.gov.au", category="abs_anzsco", client=client
    )
    for row in parse_abs_titles(abs_bytes).rows:
        key = (normalize_title(row.title), "ABS_ANZSCO")
        staged.setdefault(key, OccupationTitle(
            title=row.title, title_normalized=key[0],
            occupation_code=row.occupation_code, title_source="ABS_ANZSCO",
            anzsco_edition=row.anzsco_edition, source_url=abs_url,
            retrieved_at=retrieved_at, reliability_tier="official_scraped",
        ))

    # LIN 19/051 is coded against ANZSCO 2013 and names occupations the
    # 2022 classification does not contain - Cabinetmaker (394111) is
    # invited in live rounds and exists only there. Adding those as
    # edition-tagged occupation rows is what lets such rounds link at all;
    # without it the crosswalk resolves the name but the FK has no target.
    #
    # Only codes ABS does not already carry are added, so 2022 stays
    # authoritative wherever the editions overlap.
    existing_codes = {c for (c,) in session.execute(select(Occupation.code))}
    edition_only = 0
    for row in parse_lin_titles(lin_html).rows:
        if row.occupation_code in existing_codes:
            continue
        session.merge(
            Occupation(
                code=row.occupation_code,
                name=row.title,
                unit_group=row.occupation_code[:4],
                code_grain="occupation",
                anzsco_edition=row.anzsco_edition,
                source_url=lin_url,
                retrieved_at=retrieved_at,
                reliability_tier="official_scraped",
            )
        )
        existing_codes.add(row.occupation_code)
        edition_only += 1
    if edition_only:
        logger.info(
            "occupation_titles: added %d ANZSCO-2013-only occupation(s) absent from 2022",
            edition_only,
        )

    written: list[OccupationTitle] = []
    for (normalized, source), row in staged.items():
        existing = session.scalar(
            select(OccupationTitle).where(
                OccupationTitle.title_normalized == normalized,
                OccupationTitle.title_source == source,
            )
        )
        if existing is None:
            session.add(row)
            written.append(row)
        elif existing.occupation_code != row.occupation_code:
            existing.occupation_code = row.occupation_code
            existing.retrieved_at = retrieved_at
            written.append(existing)
    session.commit()
    logger.info(
        "occupation_titles: %d staged, %d written", len(staged), len(written)
    )
    return written
