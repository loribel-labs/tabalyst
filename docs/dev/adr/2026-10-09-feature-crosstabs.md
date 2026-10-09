# A table of a category against a feature is a directed pair whose classes the Scan fixes

Status: accepted on 2026-10-09 (maintainer, lot 8b of the Scan and JSON work; the
maintainer approved the plan and its defaults, "oui à tout").

## Context

Lot 8a made a pair of numeric columns a candidate with a `partner`, explored on the
row sample when the plan is made and counted by the second pass with accumulators of
aligned rows (ADR `2026-10-09-pair-analyses`). The relation the specification asks for
next is a category that determines the shape of another column: a branch whose client
identifiers follow one pattern (REL-11 to REL-16). It differs from a pair of numbers in
four ways. It has a direction (the purity of a branch is not the purity of a pattern).
Its axes must be bounded before the source is read, or a table could grow while it
streams (REL-12). Several features of the same column (the pattern, the length, the
prefix of an identifier) tell nearly the same thing, and the report must not tell it
three times (REL-16). And the plan holds no value of the data, while the classes of a
prefix or of a category are values.

## Decision

- A table is a candidate of the analyzer `category_crosstab` whose `field` is the
  category and `partner` the column of the feature; `parameters.feature` is `pattern`,
  `length` or `prefix`. Its id is `category_crosstab:dataset:category>column:feature`
  (the `>` says the order matters). The planner loses its special case for Pearson: a
  `PairAnalyzer` proposes pairs, assesses, estimates and rates them, and each has its
  block in `relations` (`datasets` for correlations, `tables` for tables).
- The classes come from the Scan alone, at the plan and at the run, so that the two agree
  and nothing is created while streaming: the candidates of `derived.patterns`, the
  lengths of the exact histogram, the most frequent prefixes of the values the Scan
  lists, and for a category the most frequent values of its exact frequencies. Anything
  else is the explicit class `other`, which is always the last class and stays in the
  result when empty. The plan holds the number of classes and never their labels; the
  result holds the labels, as a table of frequencies does.
- Rows without a category, without a value to classify or with a value the feature does
  not classify are counted outside the table, by cause, and `rows = counted + excluded`
  is checked, as are the values of each column against the Scan.
- The score the planner ranks by is the bias-corrected Cramér's V (Bergsma) of the table
  on the row sample; a table with an effective dimension of 1 or less, or too few rows,
  has no score and a reason, never 0. Only the best feature of two columns is picked by
  itself (`redundant_feature` for the others); a request or a forced plan takes all of
  them, and the report prints one block per pair of columns with the leading feature
  first.
- Purity is computed in both directions from the same counts; the dominant class of a tie
  is the first one listed; the exceptions are exact counts with the first three rows of
  each cell in source order; a rule is only a `candidate` with the provenance `learned`.
- Columns are converted to codes once per batch and shared by every table that uses them
  (`CodeFeed`, as `ColumnFeed` for the pairs). The router accepts several feeds on a
  column. A complete row sample of a CSV file answers without reading the source.

## Consequences

- The Scan and the first pass are untouched: no new format revision, no cost for a user
  who never goes deeper. A deep document written by an earlier build of this work is not
  affected: a table is one more kind of result with its own key (feature and parameters,
  not the budgets).
- A category with more than `max_categories` values has an `other` row that can dominate
  its table; the report says how many rows it holds and a rule never names it.
- The length and the prefix are cheaper than the pattern and often say the same thing:
  the planner keeps one and the report groups them, but nothing is lost from the JSON.
- The analyzers of numbers and of categories now share the exploration vocabulary
  (`scope`, `rows`, `score`, `reason`), the budgets (`max_columns`, `max_work`,
  `max_candidates`, an automatic count) and the guard (`StaleSource`), so a later pair
  analysis (nullity against nullity, a category against a number) is one more
  `PairAnalyzer`.
