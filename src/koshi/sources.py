"""Single source of truth for every built source's URL and metadata.

This is a ~50-line dataclass registry — deliberately **not** the deferred
Control Plane (`docs/superpowers/specs/2026-08-16-koshi-etl-architecture.md`
§12): no new Postgres tables, no acquisition/snapshot layer, no
`source_registry.py` orchestration refactor. It exists so that as koshi
grows from 6 sources toward the 23-source catalog, a URL, its domain, and
its cadence live in exactly one place instead of being redeclared inside
whichever `syncs/*.py` module happens to need it.

See `docs/structural-review.md` Problem 2 for the rationale, and Problem 1
for why the sync functions themselves live in `syncs/`, not here.
"""
import dataclasses


@dataclasses.dataclass(frozen=True)
class Source:
    key: str
    url: str
    domain: str
    category: str
    # Extraction shape, matching the vocabulary in
    # docs/superpowers/research/2026-08-16-koshi-source-urls.md — e.g.
    # "html_grid", "hidden_field_json", "xlsx", "xlsx_pivot_cache",
    # "epub_table_positional".
    tier: str
    feeds: tuple[str, ...]  # table names this source populates
    cadence: str  # how often the source's content actually changes


ANZSCO_OCCUPATIONS = Source(
    key="anzsco_occupations",
    url="https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco",
    domain="www.jobsandskills.gov.au",
    category="anzsco_occupations",
    tier="html_grid",
    feeds=("occupations",),
    cadence="near_static",
)

ABS_ANZSCO = Source(
    key="abs_anzsco",
    url=(
        "https://www.abs.gov.au/statistics/classifications/"
        "anzsco-australian-and-new-zealand-standard-classification-occupations/2022/"
        "anzsco%202022%20structure%20062023.xlsx"
    ),
    domain="www.abs.gov.au",
    category="abs_anzsco",
    tier="xlsx",
    feeds=("occupations", "occupation_titles"),
    cadence="rare",  # per ANZSCO edition
)

LIN19051 = Source(
    key="lin19051",
    # The instrument body, one iframe-hop from the register page. The date
    # segments pin the compilation; bump them when a new compilation lands.
    url=(
        "https://www.legislation.gov.au/F2019L00278/2026-03-28/2026-03-28"
        "/text/original/epub/OEBPS/document_1/document_1.html"
    ),
    domain="www.legislation.gov.au",
    category="lin19051",
    tier="epub_table_positional",
    feeds=("occupation_titles", "occupations"),
    cadence="irregular",  # a few times a year
)

SKILLSELECT_ROUNDS = Source(
    key="skillselect_rounds",
    url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
    domain="immi.homeaffairs.gov.au",
    category="skillselect_rounds",
    tier="hidden_field_json",
    feeds=("eoi_rounds", "occupation_momentum"),
    cadence="monthly",
)

SKILLSELECT_PREVIOUS_ROUNDS = Source(
    key="skillselect_previous_rounds",
    url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/previous-rounds",
    domain="immi.homeaffairs.gov.au",
    category="skillselect_previous_rounds",
    tier="hidden_field_json",
    feeds=("eoi_rounds", "occupation_momentum"),
    cadence="monthly",
)

POINTS_CRITERIA = Source(
    key="points_criteria",
    # The catalogued URL (/points-tested) genuinely has no points table —
    # the real one is at this sibling path.
    url="https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189/points-table",
    domain="immi.homeaffairs.gov.au",
    category="points_criteria",
    tier="hidden_field_json",
    feeds=("points_criteria_reference",),
    cadence="rare",  # major policy reform only
)

PROGRAM_ALLOCATION = Source(
    key="program_allocation",
    url="https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels",
    domain="immi.homeaffairs.gov.au",
    category="program_allocation",
    tier="hidden_field_json",
    feeds=("program_allocation",),
    cadence="irregular",  # a few times a year, Budget + mid-year updates
)

BP0068 = Source(
    key="bp0068",
    url=(
        "https://data.gov.au/data/dataset/096fd157-807c-4ba0-8c63-0754cae4ba35/resource/"
        "832fe752-f672-4ce7-a5bc-bada2270496c/download/"
        "bp0068-migration-and-child-outcome-since-2015-16-to-2025-06-30-masked-v100.xlsx"
    ),
    domain="data.gov.au",
    category="bp0068",
    tier="xlsx_pivot_cache",
    feeds=("visa_subclasses", "application_funnel"),
    cadence="annual",
)

ALL: list[Source] = [
    ANZSCO_OCCUPATIONS,
    ABS_ANZSCO,
    LIN19051,
    SKILLSELECT_ROUNDS,
    SKILLSELECT_PREVIOUS_ROUNDS,
    POINTS_CRITERIA,
    PROGRAM_ALLOCATION,
    BP0068,
]
