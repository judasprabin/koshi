"""Occupation name -> ANZSCO code resolution.

SkillSelect publishes occupation names and never codes, so this is what
stands between `eoi_rounds.occupation_name_raw` and a populated
`occupation_code`.

Two sources are consulted in a fixed order:

    1. LIN 19/051  - the binding legislative instrument
    2. ABS ANZSCO  - the classification's own code/title list

Measured against a live invitation round's 140 occupations: LIN alone
resolves 132/140, ABS alone resolves 132/140, and the union resolves
140/140. Both are therefore required.

**The order is not a preference.** Three titles in that same round resolve
to different codes in the two sources:

    Management Consultant   LIN 224711   ABS 224713
    Plumber (General)       LIN 334111   ABS 334116
    Statistician            LIN 224113   ABS 224116

LIN 19/051 governs because it is the instrument migration decisions are
made under. An ABS-first implementation returns a wrong-but-plausible code
for these three and raises nothing, which is precisely the kind of silent
error this codebase's provenance rules exist to prevent.
"""

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.models.occupation_titles import TITLE_SOURCE_PRECEDENCE, OccupationTitle

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Fold a title for matching: collapse whitespace, strip, casefold.

    Needed because the sources disagree on presentation - LIN renders
    titles in lower case, ABS in title case, SkillSelect in title case with
    occasional non-breaking spaces - while meaning the same occupation.
    """
    return _WHITESPACE_RE.sub(" ", title.replace("\xa0", " ")).strip().casefold()


def resolve_occupation_code(session: Session, title: str) -> str | None:
    """Return the ANZSCO code for an occupation title, or None if unknown.

    Returns None rather than guessing: an unresolved name is recorded as
    unresolved (the round keeps `occupation_name_raw`), which is
    re-resolvable later. Inventing a code would not be.
    """
    normalized = normalize_title(title)
    matches = {
        row.title_source: row.occupation_code
        for row in session.scalars(
            select(OccupationTitle).where(OccupationTitle.title_normalized == normalized)
        )
    }
    if not matches:
        return None

    for source in TITLE_SOURCE_PRECEDENCE:
        if source in matches:
            if len(matches) > 1 and len(set(matches.values())) > 1:
                logger.info(
                    "crosswalk conflict for %r: %r - using %s per precedence",
                    title, matches, source,
                )
            return matches[source]

    # A source outside the precedence list; the CHECK constraint should make
    # this unreachable, so log rather than silently picking one.
    logger.warning("crosswalk: title %r has no source in precedence order: %r", title, matches)
    return None
