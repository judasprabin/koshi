"""Parser for JSA's Occupation Shortage List (data model C18).

Two-step source, unlike koshi's other pages. source-urls.md §10 describes
the rating data as "splData/splSearch JSON embedded in the page" — stale,
predating a site redesign. The actual data lives in a separate static
JSON file (`splData.json`, ~1.4MB) whose current path is only
discoverable from the page's own Drupal settings config
(`<script type="application/json" data-drupal-selector="drupal-settings-json">`),
and the filename changes whenever JSA republishes — it's literally
timestamped ("25-10-10 - splData (1).json").

The payload nests four dimensions the original C18 spec didn't account
for (confirmed against the live file, not assumed):

    splData[code_grain][edition][occupation_code] = {
        "c": <code>, "t": <title>, "l": <level>,
        "v": {
            "<year>": {
                "rnat": <rating>, "rnsw": <rating>, ..., "ract": <rating>,
                "d": <future demand, always null>,
            },
            ... one entry per year, 2021 onward ...
        },
    }

- code_grain: "4" (unit group) or "6" (occupation) — this build uses "6",
  koshi's primary occupation grain.
- edition: "2022" (ANZSCO) or "2024" (OSCA) — this build uses "2022";
  OSCA is deferred to the same ANZSCO->OSCA migration trigger already
  tracked as issue #13.
- jurisdiction: national + 8 states/territories, each independently
  rated — the audit's "the M/R split is itself geographic" finding,
  confirmed live: e.g. Beef Cattle Farmer (121312) rates NT=S while every
  other jurisdiction reads NS. A schema keyed on occupation_code alone
  would collide these.
- year: a real multi-year time series (2021 onward). This build takes
  only the latest year present per occupation — a full history isn't
  needed for a "current shortage status" fact and would multiply row
  count five-fold for no near-term product use.
"""

import dataclasses
import json
import logging
import re

logger = logging.getLogger(__name__)

_JURISDICTION_FIELDS = {
    "rnat": "NAT", "rnsw": "NSW", "rvic": "VIC", "rqld": "QLD",
    "rsa": "SA", "rwa": "WA", "rtas": "TAS", "rnt": "NT", "ract": "ACT",
}
_VALID_RATINGS = {"S", "M", "R", "NS"}

_DRUPAL_SETTINGS_RE = re.compile(
    r'<script type="application/json" data-drupal-selector="drupal-settings-json">(.*?)</script>',
    re.S,
)


class SkillsPriorityError(ValueError):
    """The page or data file did not have the expected shape."""


@dataclasses.dataclass
class SkillsPriorityRow:
    occupation_code: str
    jurisdiction: str
    shortage_rating: str
    future_demand_rating: str | None


@dataclasses.dataclass
class ParseResult:
    rows: list[SkillsPriorityRow]
    skipped: int


def discover_spl_data_path(page_html: str) -> str:
    """Find splData.json's current path from the page's Drupal settings.

    The filename is timestamped and changes whenever JSA republishes, so
    this must be re-discovered on every sync rather than hardcoded.
    """
    match = _DRUPAL_SETTINGS_RE.search(page_html)
    if match is None:
        raise SkillsPriorityError(
            "drupal-settings-json script tag not found - possible page redesign"
        )
    try:
        settings = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SkillsPriorityError(f"drupal-settings-json is not valid JSON: {exc}") from exc

    try:
        path = settings["applets"]["applet_data"]["spl_data"][2]
    except (KeyError, IndexError, TypeError) as exc:
        raise SkillsPriorityError(
            f"expected applets.applet_data.spl_data[2] in drupal settings, "
            f"got keys {sorted(settings.keys())!r} - possible page redesign"
        ) from exc
    return path


def parse_skills_priority_ratings(
    spl_data_json: str, *, code_grain: str, edition: str
) -> ParseResult:
    """Parse splData.json for one (code_grain, edition) combination.

    A combination absent from the payload (e.g. 4-digit/2024, genuinely
    empty in the live source) yields zero rows, not an error — that's a
    real "nothing published here" state, not a redesign signal.
    """
    try:
        payload = json.loads(spl_data_json)
    except json.JSONDecodeError as exc:
        raise SkillsPriorityError(f"splData.json is not valid JSON: {exc}") from exc

    occupations = payload.get(code_grain, {}).get(edition, {})

    rows: list[SkillsPriorityRow] = []
    skipped = 0
    for code, entry in occupations.items():
        years = entry.get("v", {})
        if not years:
            skipped += 1
            continue
        latest_year = max(years, key=int)
        ratings = years[latest_year]
        future_demand = ratings.get("d")

        for field, jurisdiction in _JURISDICTION_FIELDS.items():
            raw = ratings.get(field)
            if raw is None:
                skipped += 1
                continue
            normalized = raw.strip().upper()
            if normalized not in _VALID_RATINGS:
                logger.warning(
                    "skills_priority: unrecognized rating %r for %s/%s - skipping",
                    raw, code, jurisdiction,
                )
                skipped += 1
                continue
            rows.append(
                SkillsPriorityRow(
                    occupation_code=code,
                    jurisdiction=jurisdiction,
                    shortage_rating=normalized,
                    future_demand_rating=future_demand,
                )
            )

    logger.info(
        "skills_priority: %d rows (%s/%s), %d occupations, %d skipped",
        len(rows), code_grain, edition, len(occupations), skipped,
    )
    return ParseResult(rows=rows, skipped=skipped)
