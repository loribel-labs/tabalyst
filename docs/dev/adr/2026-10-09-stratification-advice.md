# Stratification advice is a part of the plan, and the classic stratified sample keeps its meaning

Status: accepted on 2026-10-09 (maintainer, lot 9 of the Scan and JSON work; the
maintainer approved the plan and its defaults with "ok").

## Context

`tabalyst sample --sample-method stratified` allocates rows to the values of one
field in proportion to their size. Nothing told a user which columns make good
strata, nor that two columns multiply: 200 countries by 2,000 products by 30 channels
is twelve million possible strata, and the sample held one counter and one reservoir
per stratum without a limit. The specification (D16, D17, STRAT-01 to STRAT-08) asks
for advice before the sample, a risk that does not overflow or pretend to be a fact,
a ceiling of states at run time, and a classic `stratified` that does not become a
"coverage" mode with a minimum of one row.

The advice could be an analyzer of the second pass, a block of the Scan, or a part of
the plan. It needs no reading of the source: the cardinalities, the frequencies and the
row sample of the Scan are enough, and a recommendation is not a fact of the data
(specification 11.1).

## Decision

- The advice is a member of the plan, `stratification`, computed by
  `planner/stratification.py` from the Scan alone when a request is made
  (`Stratify`). It is not an analyzer: no executor, no part in the selection, not
  written in the second-pass document. A plan without the request is unchanged,
  `plan_id` included. The Scan, its format and the first pass are not touched.
- The arithmetic shared with the sample lives in `scanner/stratify.py`: the classic
  allocation (moved unchanged), a saturating product that never overflows and says
  that it saturated, and the sample size from which the rarest stratum cannot get zero.
- A product of cardinalities is a certain bound only when it is made of certain
  maxima, capped by the records. A product of estimates is published apart and labelled
  an estimate. The row sample gives a lower bound of the combinations that exist, or
  the exact number when it holds every row.
- The risk (low, moderate, high, excessive) uses fixed thresholds recorded in the plan
  (1,000, 10,000 and 100,000 strata), not a measured time. A high risk proposes
  reducing the columns, setting an explicit limit or using smart sampling; it does not
  stop anything by itself.
- The sample accepts several fields (strata are tuples of cells, so a joined text never
  collides), counts its strata before reading rows again and stops with an error at
  `max_strata` (100,000 by default), and reports the strata known, sampled and left
  without a row. The allocation and the rounding are those it always had.
- A missing value is a stratum of its own, as the sample always made it, and the advice
  declares it.

## Consequences

- A user asking for the advice pays one planning pass over the Scan in memory, and the
  classic sample pays one more comparison per new stratum.
- A file with more than 100,000 strata, which the old `stratified` accepted, now stops
  unless `--max-strata` is raised. This is the ceiling STRAT-08 asks for.
- The thresholds are constants of version 1 of the advice. They can become settings
  when a use shows they need to move; changing them changes the advice, not any result.
- `sample` does not read a stored Scan to refuse an excessive risk by itself: that
  belongs to the lot that makes Sample use Scan (D23). The Report prints nothing of the
  advice yet.
