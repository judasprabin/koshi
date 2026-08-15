# koshi — Data Sources Reference

**Status:** Living reference — derived from
[`docs/superpowers/specs/2026-08-14-koshi-design.md`](superpowers/specs/2026-08-14-koshi-design.md)
§3–§5. Update this file whenever the spec's data model or source list changes;
don't let the two drift.
**Date:** 2026-08-15 (implementation-status section added 2026-08-15 after
the occupation slice merged)
**Author:** Prabin Karki, via Claude

## How to read this

Every row below is one real-world source in the crawler's 19-domain config,
not a paraphrased category. **Feeds** names the Postgres table(s) and key
fields (§3) that source populates. **Tier** is the `reliability_tier` that
row is stored and served with — see the legend before the catalog.

This catalog describes the design spec's *full* intended source list —
16 sources. It is not a status report on its own; the section immediately
below is. Don't read every row as "implemented" — most aren't yet.

## Implementation status

Only 4 of the 16 sources below have real extraction code today (the
occupation vertical slice — see `docs/ARCHITECTURE.md`). Everything else in
the catalog is spec-only: a real, researched source with a table ready to
receive it, but no parser or curation pipeline built against it yet.

| Source (catalog row) | Status | Code |
|---|---|---|
| ANZSCO codes/names | ✅ Implemented — `official_scraped` | `src/koshi/extraction/anzsco_occupations.py` |
| EOI thresholds, invitations issued | ✅ Implemented — `official_scraped` | `src/koshi/extraction/skillselect_rounds.py` |
| Occupation ceilings, program allocation | ⚠️ Partially — only `ceiling_usage.issued`/`.ceiling` per occupation, hand-curated for 2 example occupations, not the full `program_allocation` table (stream splits, total places) | `src/koshi/seeds/ceiling_usage_manual.yaml` + `src/koshi/seeds/loader.py` |
| Occupation momentum | ✅ Implemented — `derived`, computed not scraped | `src/koshi/momentum.py` |
| Everything else (12 rows below) | ❌ Not started — table exists in the spec's data model (where applicable), no extraction/curation code | — |

The crawler's own infrastructure (`source_pages`, content-hash
change-detection, the extraction watermark) is fully general — pointing it
at a 5th source is adding a parser and a `pipeline.py` sync function, not
building new plumbing. See `docs/ARCHITECTURE.md` §3.

## Reliability tiers

| Tier | Meaning |
|---|---|
| `official_scraped` | Deterministic parser against a structured, official page. |
| `official_curated` | Official source, but the page resists clean parsing — a person reviews and enters the value on a cadence. |
| `community_sourced` | Non-government source, used only where no official one exists; always visibly labeled to the frontend. **Not used by any source below yet.** |
| `derived` | Computed from koshi's own rows — cites the rows it was computed from, not an external URL. |
| *(none assigned)* | Sourcing unconfirmed — the spec withholds a tier rather than assign one to an unverified fact. Used once below (points distribution). |

## Source catalog

| Source type | Real source | Format | Cadence | Tier | Feeds |
|---|---|---|---|---|---|
| EOI thresholds, invitations issued | `immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds` | HTML table, per round | ~monthly | `official_scraped` | `eoi_rounds` — threshold_points, invitations_issued, round_date |
| Occupation ceilings, program allocation | `immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels` | Periodic report (PDF) | Irregular, few/yr | `official_curated` ⚠ | `ceiling_usage` — ceiling · `program_allocation` — places, stream_name |
| Visa fees | `immi.homeaffairs.gov.au/visa-fees` | HTML table | Irregular (indexation) | `official_scraped` | `visa_subclasses` — base_application_cost |
| Points test criteria | `immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/points-test` | HTML | Rare | `official_scraped` | `points_criteria_reference` — criterion_name, band_description, points_value |
| Visa subclass static facts (189/190/491/485/500/482) | Individual Home Affairs visa subclass pages | HTML prose, page-specific | Rare | `official_curated` | `visa_subclasses` — name, family, permanence, age_limit, work_rights_description, family_inclusion_rule, residency_requirement_description, occupation_list_required, onward_pathway_code, points_test_required |
| Health / character / English requirement reference | `immi.homeaffairs.gov.au/help-support/meeting-our-requirements/{health,character,english-language}` | HTML prose | Rare | `official_curated` | **No table named in spec** ⚠ |
| Processing times | Home Affairs "Global Visa Processing Times" page | HTML table | ~monthly | `official_scraped` | `processing_times` — median_days, as_of_date |
| MLTSSL / STSOL / ROL list membership | `legislation.gov.au` (legislative instruments) | HTML / gazette-style | A few/yr | `official_scraped` | `list_change_log` — list_name, change_type, effective_date |
| ANZSCO codes/names | `jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco` | HTML | Near-static | `official_scraped` | `occupations` — code, name, unit_group |
| Skills priority list | `jobsandskills.gov.au/skills-priority-list` | HTML / dataset | Annual | `official_scraped` | **No table named in spec** ⚠ |
| State nomination status/criteria (NSW/VIC/QLD/WA/SA) | State government pages (crawl list) | HTML landing pages | Irregular | `official_curated` ⚠ | `state_nomination_status` — status, fee, points_minimum, job_offer_required, residency_commitment_description, decision_time_estimate, documents_required, approval_pattern_note |
| State occupation list changes | Same state pages, via crawler diff | HTML | Irregular | `official_curated` | `list_change_log` — list_name = state code, change_type, effective_date |
| Assessing bodies × occupations | `mara.gov.au` / individual assessing-body sites | HTML | Rare | `official_curated` ⚠ | `assessing_bodies` — body_name, turnaround_estimate, cost · `occupation_assessing_bodies` — join |
| Policy events (trend annotations) | Ministerial press releases · `budget.gov.au` · `treasury.gov.au` | HTML | Ad hoc | `official_curated` ⚠ | `policy_events` — event_date, visa_code, description |
| Application funnel — submitted/invited | SkillSelect round-results pages | HTML table | ~monthly | `official_scraped` | `application_funnel` — submitted_count, invited_count |
| Application funnel — granted, by pathway | Home Affairs annual report | PDF, aggregate | Annual | `official_curated` ⚠ | `application_funnel` — granted_count (may launch `NULL`) |
| Points distribution among invitees | **No confirmed source in any of the 19 crawled domains** | — | — | *(none assigned)* ⚠ | `points_distribution` — deferred, not built in v1 (§3.4) |
| Occupation momentum | Computed from koshi's own `eoi_rounds` | — | Nightly job | `derived` | `occupation_momentum` — direction (rising/falling/steady) |

**Not a source:** `source_pages` (§5) is the crawl registry itself — url,
content_hash, last_changed_at, etc. — not a fact table. It's what the sources
above are checked *against*, so it carries no `reliability_tier`.

## Sources that need review

Carried forward from the spec's own §2, §4, and §11 rather than smoothed
over — each is a real gap or open decision, not resolved by this file.

**Not yet in the crawler's 19-domain config — need adding:**
- [ ] Assessing bodies (`mara.gov.au` / assessing-body sites)
- [ ] Policy events (ministerial press releases / `budget.gov.au` / `treasury.gov.au`)

**Confirmed source, no schema table to receive it — need a decision:**
- [ ] Health / character / English requirement reference pages — closest
      candidate is `english_test_bands`, but the spec never assigns it there
- [ ] Skills priority list — no table named anywhere in §3

**Likely more than a lookup — extraction approach needs design, not just a parser:**
- [ ] Occupation ceilings / program allocation — the planning-levels report
      is periodic and PDF-based; per-occupation `ceiling_usage.ceiling` may
      require cross-referencing the published cap against SkillSelect
      invitation counts rather than reading one number off one page
- [ ] State nomination status/criteria — state pages are general "how to
      apply" landing pages, not per-occupation data tables; the rich detail
      the mockup needs will most likely require a human-curated seed
      (`bato`'s pattern), reviewed against the source on a cadence, not a
      parser that looks automated but silently breaks on a page redesign

**Weakest-sourced field — may need to ship incomplete rather than approximate:**
- [ ] `application_funnel.granted_count` — pathway-level breakdown may not be
      published at all; launch `NULL` where unconfirmed instead of a
      fabricated number

**Deferred entirely, revisit if a source turns up:**
- [ ] Points distribution among invitees (`points_distribution`) — not built
      in v1; would need either an official source or a clearly-labeled
      community tracker before the table is created at all
