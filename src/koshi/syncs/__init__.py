"""One sync module per source (docs/structural-review.md Problem 1).

Each module owns exactly one `sync_*` function and imports its URL from
`koshi.sources` rather than defining its own constant. `koshi.pipeline`
re-exports every sync function from here, so this split is invisible to
existing callers (`koshi.__main__`, `tests/test_pipeline.py`) — only the
file each function's *body* lives in has moved.

Shared helpers used by more than one sync module (`_needs_extraction`,
`_RowsWithSkipCount`, `_persist_rounds`, `resolve_round_occupation_codes`,
`refresh_momentum_for_codes`) stay in `koshi.pipeline` — moving them here
would just relocate the god-module problem one level down.
"""
