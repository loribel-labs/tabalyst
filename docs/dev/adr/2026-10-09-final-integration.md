# The last open points of the Scan and JSON work are closed in one integration lot

Status: accepted on 2026-10-09 (maintainer, lot 11 of the Scan and JSON work).

## Context

Lots 8b to 10b left four points open: the stability of a table of counts was judged but not used by the planner,
a pair of equivalent columns was printed in both directions as two phenomena, the report of a smart sample had no
page, and what Explore may rely on in the documents was written nowhere. The Report overhead (+107%) was left for
the maintainer to weigh.

## Decision

- The planner ranks a table by `(unstable, -score, -rows)`: an unstable table comes after every stable one and is
  never dropped for that reason. *Amended by lot S3a (2026-10-14):* the key is `(weak, redundant, unstable, -score,
  -rows)` (`weak`: V below 0.45): a strong unstable table, such as a near-functional dependency between two
  columns, ranks before the weak stable ones, and the redundant features of a pair rank after the first feature of
  the other pairs, so that they do not fill the list.
- The report folds the weaker direction of a pair listed in both directions under the stronger one. No count is
  merged and the documents do not change.
- `tabalyst sample --sample-method smart` writes `<stem>.sample.html` from the `tabalyst.sample` document alone,
  as `tabalyst scan` writes its page (`--no-html` skips it). The page is not part of the format.
- What Explore consumes of a Scan, a Report and a second pass is a contract (design 20.17), kept true by tests.
- `_family` of the smart selection stays a copy of `technical.string_family`, and the `stratified` guard keeps
  hashing the source: removing either touches the hot path of the first pass or weakens the identity check.

## Consequences

- An automatic choice of tables spends its budget on stable tables first.
- A reader sees one block for two directions of the same pair, and can open the other.
- A change of the profile that takes a facet away from Explore fails a test.
- The two copies of the classification of a cell can drift; the verification of a smart sample reports a
  disagreement with the Scan instead of producing a wrong sample.
