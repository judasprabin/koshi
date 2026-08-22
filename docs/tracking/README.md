# koshi tracking CSVs

Three spreadsheet-friendly CSVs for tracking sources, tables, and columns —
open in Excel/Numbers/Sheets, sort/filter/pivot freely. These are a
**generated view**, not a new source of truth: the underlying facts live in
the docs and the database. If you edit koshi's schema or sources, regenerate
rather than hand-editing these out of sync.

| File | Grain | Rows |
|---|---|---|
| `koshi-sources.csv` | One row per concrete source URL (23 catalogued sources, some split into per-page rows — e.g. the 6 visa-subclass pages) | 45 |
| `koshi-tables.csv` | One row per table (22 domain tables + 6 control-plane + 5 data-plane = 33) | 33 |
| `koshi-columns.csv` | One row per column across every table, built and target | 286 |

## Where the data comes from

- **BUILT tables' columns** (`occupations`, `eoi_rounds`, `ceiling_usage`,
  `occupation_momentum`, `source_pages`, `visa_subclasses`,
  `application_funnel`, `occupation_titles`) — pulled directly from
  `information_schema.columns` / `information_schema.table_constraints`
  against the local `koshi` database, **not** transcribed from prose. This
  is ground truth by construction: it cannot drift from the doc's
  description because it bypasses the doc entirely.
- **Row counts** — `pg_stat_user_tables`, as of 2026-08-21.
- **TARGET/DEFERRED tables' columns** — transcribed from
  `../superpowers/research/2026-08-16-koshi-data-model.md`'s per-table
  column tables (sections A1–A6, B1–B5, C1–C22).
- **Sources** — transcribed from
  `../superpowers/research/2026-08-16-koshi-source-urls.md`'s 23 per-source
  sections, plus `pipeline.py`'s URL constants for the 6 built sources
  (more exact than the doc's shorthand — e.g. the doc says "ABS ANZSCO
  release", `pipeline.py:ABS_ANZSCO_URL` has the literal `.xlsx` URL).

## How to regenerate

The build script is
`/private/tmp/claude-501/.../scratchpad/build_koshi_csvs.py` from the
session that created this — it won't survive that session's scratchpad
cleanup. To regenerate from scratch in a future session:

1. Re-run the `information_schema` queries in this file's git history
   (search for `koshi_columns_raw.csv` in the commit that added this
   directory) against the live `koshi` database for the BUILT tables.
2. Re-read `2026-08-16-koshi-data-model.md` for any TARGET/DEFERRED table
   whose spec changed.
3. Re-read `2026-08-16-koshi-source-urls.md` for any source whose status
   changed (most likely: a VERIFIED source moving to BUILT once it ships).
4. Diff against the existing CSVs rather than starting over — most rows
   won't have changed.

## Known gaps (be honest about these when using the CSVs)

- Sources 18 (ABS OSCA correspondence workbook), 19, and 23
  (legislation.gov.au OData endpoint) don't have a fully pinned literal
  URL in `source-urls.md` yet — the `url` column says so explicitly rather
  than guessing one.
- `koshi-tables.csv`'s `live_rows_2026_08_21` column is blank for every
  TARGET/DEFERRED table by definition — they don't exist yet, not that
  the count is unknown.
- This snapshot is dated **2026-08-21**. Row counts and BUILT/TARGET
  status will drift as the pipeline runs and new sources ship — re-check
  before relying on a specific number for anything time-sensitive.
