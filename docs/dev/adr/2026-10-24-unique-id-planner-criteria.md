# The planner chooses the Deep counts of the uniqueness of an identifier by itself, within the automatic budgets

Date: 2026-10-24 (lot 8 of the Unique ID plan)

## Context

Lots 6 and 7 gave the second pass two analyses that settle the uniqueness of an identifier after row deduplication:
`duplicate_rows_count` (the extra copies of whole rows, exact) and `analytical_distinct` (the distinct values after NFC,
trim and whitespace, exact). Both had a utility of 40, under the 45 an automatic choice needs, so only `--deep` or a
request ran them. UID-011 asks that the plan run them when it is needed and not otherwise, with its interest, cost and
reuse written in the plan (cahier 12.1 to 12.5). The planner reads the Scan only, and the rule "smart by default,
explicit when costly" forbids a silent long operation and any decision from a measured time.

## Decision

- **Which column.** `FieldFacts.uniqueness_candidate`: the Scan gives the column the role `identifier/id` (a raw
  `unique_id` needs no count of the copies), every position holds a value (lot 10 widens this for a CSV file to a column
  that lacks a value, ADR `2026-10-25-missing-id-copies`), it is not under an array, no record was left
  out and the dataset has two records at least. These are the cases of the cahier 12.1 that need no second pass.
- **Utility.** For a candidate, `analytical_distinct` has a utility of 50 (`identifier_uniqueness`) and
  `duplicate_rows_count` 50 (`identifier_copies`) when the Scan's count is a lower bound. Everything else of the
  automatic choice stays as it is: the memory (128 MiB), the CPU class, the cells of the reading. No new setting.
- **Order.** The count of the copies is decided after the other analyses: it is worth it only when the distinct count of
  an identifier column of the dataset is exact in the Scan or selected in the same plan (`Analyzer.gives_distinct`).
  Otherwise the reason is `distinct_unknown`.
- **CPU class of whole rows.** The unit of `duplicate_rows_count` is the record, so its class is that of its share of a
  cell (`NS_PER_CELL["rows"]` divided by the number of columns), the unit of the classes. `cell_ns` stays per record for
  the time estimate. A table of three columns or more is `moderate`, a table of two is `high` and is left to `--deep`,
  which asks first; a small wide table forced no longer asks.
- **Proof first.** `plan_analyses(..., proved_copies=...)`: a valid Dedup report (explicit or colocated) makes the
  candidate `already_satisfied` (`copies_proved`). The Report validates the proof before it plans.
- **Cache.** The version of the analyzer is the version of its calculation (`dedup.calculation.CALCULATION_VERSION`;
  `analytical.CALCULATION_VERSION`), part of the key of a result. A stopped count of the copies is reused at the same key
  (its ceilings are bytes and records, so it stops at the same place anywhere); a stopped set of values is not (the memory
  the plan granted is no part of its key).
- **No shared reading.** The two analyses keep their own reading: the count of the copies uses the strict CSV reading of
  Dedup, which the router's reading is not (ADR `2026-10-24-dedup-count-only-for-deep`). The cost of the second reading is
  measured in the contract (section 12) instead.

## Consequences

- A `tabalyst report` of a file of a few hundred thousand records with an identifier column concludes by itself where it
  could not before; the automatic count is expected to stay in memory (the estimated table of distinct rows is bounded by
  the automatic memory; the ceilings of `deep.copies` still apply if the estimate is exceeded). Above that size the conclusion needs `--deep` (which asks), a Dedup report, or a Scan that
  tracked the file whole.
- The plan states the interest (`identifier_uniqueness`, `identifier_copies`), the cost and the reuse of each candidate;
  a count that waits for a missing distinct count says so (`distinct_unknown`).
- `COST_MODEL_VERSION` changes (the class of the rows); a stored second-pass document stays valid (the analyzer versions
  are unchanged at 1).
- Rejected: an own budget of records for the automatic count (the memory budget already bounds it; the measures of the
  contract say whether it should be raised), choosing the count of the copies without a distinct count (it would settle
  nothing), a pass that reads the file once for both analyses.
