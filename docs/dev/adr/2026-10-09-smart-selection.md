# The rows of a smart sample come from a bounded pool of candidates and a greedy cover

Status: accepted on 2026-10-09 (maintainer, lot 10b of the Scan and JSON work; the maintainer approved the plan
and its defaults).

## Context

The plan of lot 10a says what a smart sample aims at (targets, weights, reserve, budget of candidate rows). The
selection has to find the rows in a file that does not fit in memory, cover the mandatory targets when the size
allows it, keep ordinary rows, write whole rows (a preview is not a row) and tell what it covered. A target can
only be recognized on a row by reading the cell as the first pass did, and two readings that disagree would make
the report wrong without anyone noticing.

## Decision

- One reading, after the plan: a row is tested against the targets while it streams; a second pass and the
  selection are never merged (a row rejected before a statistic was known cannot be chosen afterwards).
- A bounded pool: a few candidates per target, chosen by a seeded hash of the position, so the result does not
  depend on the batches; one copy of a row; whole rows in a byte budget, with the optional targets limited to
  80% of it. What does not fit is refused and counted, never shortened.
- A greedy cover on the pool, mandatory targets first, then the weight not yet covered; a bottom-k reserve of
  ordinary rows takes what is left. It is a heuristic and says so.
- The tests on a row reuse the first pass's reading of a cell, the coders of the patterns and of the tables, and
  the rules of the second pass. The report **verifies** them: for every exact frequency of the plan it counts the
  rows found and lists any difference.
- The report is a document of its own, `tabalyst.sample`, beside the CSV file. It names the coverage as that of
  the catalog of targets.
- The time of the selection is estimated and confirmed like a second pass (rule R1), outside the plan.
- `stratified` reads a current stored Scan, never makes one, to stop a run whose strata are excessive; an
  explicit `--max-strata` allows it.

## Consequences

- Memory does not grow with the file: the pool is bounded and the reading holds one batch (measured: +5 MB over
  the loaded Scan on a million rows).
- The selection reads the source as slowly as a single-process second pass: about 35 s on the 1 million row
  reference file, against a first pass of 5.7 s of reading. It asks before it passes 2 minutes.
- Any change in how the first pass reads a cell shows in the verification of the report rather than in a wrong
  sample.
- A format `tabalyst.sample` joins Scan, Report and the second pass: it needs its schema, its page and its
  changelog.
- The HTML page of a scan and of the report of a sample are not part of this decision.
