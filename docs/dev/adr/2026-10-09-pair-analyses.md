# A pair of columns is a candidate with a partner, explored on the sample when the plan is made

Status: accepted on 2026-10-09 (maintainer, lot 8a of the Scan and JSON work; the
maintainer asked the assistant to decide and followed the recommendations).

## Context

Every analysis the planner and the executor knew concerned one field: the
candidate has one `field`, its id is `analyzer:dataset:field`, the key of a stored
result and the routing of the reading are by field. The correlation of two numeric
columns (REL-04 to REL-09) needs three things that do not fit it. A pair needs the
values of the same record in two columns. The number of pairs is quadratic, 4,950
for 100 columns, so it cannot be a candidate per pair, and so the planner must first
decide which pairs are worth counting. And its coefficient is only meaningful on the
rows where both values are numbers, not on the means of each column.

Three places could hold the choice of the pairs: the first pass (a fixed cost for
everyone, against the principle that the Scan is not made heavier), the Scan as a
`derived` block (a new format of the Scan for a number the second pass improves),
or the planner. Only the planner already reads the Scan and nothing else, and
produces a deterministic document that holds no value of the data.

## Decision

- A candidate of a pair has `partner` (the second field, after the first in the
  order of the dataset) and `exploration`, what the row sample says of the pair.
  Its id is `analyzer:dataset:first+second`, its `display` names both, and the key
  of its result includes the partner. The members are left out when absent, so the
  plans, documents and keys of the single-field analyses do not move.
- The exploration is made when the plan is made (`planner/relations.py`), from the
  row sample of the Scan in memory. It scores all the pairs of the eligible columns,
  lists the best ones as candidates (`max_candidates`) and describes what it did in
  a `relations` member of the plan: columns explored and left out by reason, pairs
  scored and undefined by reason, work spent. A pair that was asked for and not
  listed becomes a candidate too (REL-06). Nothing is added to the format of the
  Scan, and the first pass is not touched.
- The exploration bounds its own cost with deterministic quantities (columns, and
  pairs times rows compared, COST-05), not a measured time. Its figures are rounded
  to six decimals so that the plan is the same on any machine.
- A pair is ranked by the lower end of the 95% interval of its coefficient, so that
  a few rows do not outrank many. The utility of the planner is 100 times that bound.
- The reading converts each numeric column once per batch (`ColumnFeed`) and hands
  the aligned rows to each pair that uses it (`PairAccumulator`). The accumulator
  keeps count, means, sums of squares and cross products of the common rows, merged
  batch by batch (Chan et al.), with the minimum and maximum of each column, since a
  constant column is the one whose minimum equals its maximum and no rounding can
  hide that. Arithmetic is float64: the counts are exact, the coefficient is
  `precision: "float64"`.
- When the Scan holds every row (a complete sample of a CSV file), the pair is
  computed from the sample and the source is not read, as the patterns are.

## Consequences

- The Scan and the first pass stay as they were: no new format revision of the
  Scan, no cost for a user who never goes deeper.
- A plan made from a Report is refused as before (the Report's samples are reduced),
  so an exploration always sees the full row sample. A plan made from a scan document
  on disk sees it too.
- The plan carries the figures of the sample, derived data and no value of the data.
  A reader of a plan can see why a pair was chosen or not.
- An exact arithmetic (fractions) would be about fifty times slower and is not
  needed: the oracle of the tests is exact, and the coefficient agrees with it to
  1e-12.
- Category-to-pattern relations (lot 8b) use another kind of accumulator and the same
  structures (candidate with partner, `relations` block, shared column feeds).
