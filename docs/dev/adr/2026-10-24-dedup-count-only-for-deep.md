# The Deep copies of rows use a count-only mode of the Dedup engine

Date: 2026-10-24 (lot 6 of the Unique ID plan)

## Context

The Report separates the repetitions of an ID that exact copies of rows explain from those that remain between
distinct records (ADR `2026-10-23-identifier-uniqueness-derived-in-report`). It needs the exact number of extra
copies of rows. The Scan holds it only up to `limits.max_tracked_records`, and a Dedup report exists only if the user
ran `tabalyst dedup`. The project rule is smart by default, explicit when costly: a long reading is never silent.
Calling `dedup_csv` from the second pass would write `.unique.csv`, `.duplicates*.csv` and a report beside the source.

## Decision

- `dedup/count_only.py` offers `count_extra_copies`: the same canonical key, exact store and strict reading as
  `analyze_dedup`, with no output, no marks of records and ceilings of its own (`memory_mb`, `disk_mb`,
  `max_rows`, the settings `deep.copies`). A ceiling stops the reading and the result is a lower bound
  (`limited`), never a count. The disk ceiling is estimated from the accounted key bytes, not measured, so a file
  stops at the same record on any machine.
- The second pass gets the analyzer `duplicate_rows_count`, one candidate per CSV source with one dataset (the field
  `$`, as `structure_variants` has for JSON, through `Analyzer.rows`). It reads the file on its own, outside the
  router and the workers: the result is the one of `tabalyst dedup` and does not depend on the number of workers.
  The saving of sharing the reading of the router is left to the planner lot (lot 8).
- It never overrides a Scan set not to count (`records.duplicates: false`), is `already_satisfied` when the Scan
  counted exactly, and is never chosen by itself (utility 40): asked for, or forced.
- The Report reads its result as the third source of `E`, after the Scan and a Dedup report, with a distinct source
  name in the evidence and the same conflict rule.

## Consequences

- A file whose Scan count is limited gets a complete conclusion from `report --deep`, at the price of a second
  reading, which a forced run announces and confirms (CPU class above the automatic limit).
- Two code paths (`analyze_dedup`, `count_extra_copies`) share the key, the store and the helpers of the source
  checks; tests keep them equal on adversarial files.
- The second-pass document goes to revision 4 (a new result kind and settings member).
- Rejected: calling `dedup_csv` into a temporary folder (writes, deletions and a report to manage), feeding the rows
  of the router to the store (the Scan's reading is not the strict CSV reading of Dedup, so equality with
  `tabalyst dedup` would no longer be exact by construction).
