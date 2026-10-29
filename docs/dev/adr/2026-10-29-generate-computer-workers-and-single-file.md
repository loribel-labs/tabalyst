# Computer rows come from cached selection, worker processes and one file per run

Date: 2026-10-29 (release 0.7.3)

## Context

Generating 30,000 Computer rows with an anomaly profile took 486 s. A profile showed 97 % of the time in
`select_catalog_row`, which searched the feasible completions of every candidate from scratch for every row and
revalidated all the constraints. The command also wrote nine files even for a user who wanted one CSV with errors, and
it required both locales although `--locales` was documented. A long operation must not be silent (design rule smart
by default, explicit when costly).

## Decision

- Feasibility, candidates, derivations and the weighted choice of each step are cached per package, dataset and
  generation profile (`generate_selection._SelectionPlan`). The key of a cache entry is the position and the values of
  the fields that the remaining steps and the constraints read, never the seed or the row index, so one row's search
  serves the others. The random draw is unchanged: output is byte for byte what the uncached code wrote. An impossible
  configuration is reported by an uncached search, which keeps its detail.
- Rows are rendered by worker processes from 5,000 rows (`generate_computer_parallel.py`, `--workers`). A row depends
  only on its number, so spans of row numbers are rendered to part files and appended in order. The workers reuse
  Scan's subprocess helper rather than `multiprocessing`, which would re-import a calling script without a main guard.
  The count follows the existing rule of Scan (one per spare processor, at most 6, 1 in a frozen program) and never
  changes the output.
- `-o` and one locale are valid for Computer; one anomaly profile with `-o` writes the errors and `FILE.changes.csv`.
  Several profiles share one generation of the rows and need `-d`.
- `generate_datasets` takes `on_progress` and the result carries the total time and its split. The CLI shows a
  rewritten line only on a terminal and always prints the timing line.

## Consequences

- 30,000 rows take about 17 s in one process and about 8 s with three; 1,000,000 rows about 3 min with three
  processes, at 70 to 80 MB of memory. Time is linear in the number of rows.
- The caches live for the life of the process and are bounded to eight plans; a worker pays about half a second to start.
- `ComputerPlan.anomaly_profile` became a property over `anomaly_profiles`; the metadata layout of several profiles
  differs from that of one, which keeps its earlier layout.
- Error injection stays sequential (about 15 % of a large run): splitting it would need the exact-count operations to
  be chosen before the rows are split.
