# The copies of the rows without an ID are counted apart, in a light mode, to decompose despite missing IDs

Date: 2026-10-25 (lot 10 of the Unique ID plan)

## Context

With a missing ID the extra copies of whole rows (`E`) mix copies of rows that have an ID, which explain a
repetition of the ID, and copies of rows that have none, which explain nothing (cahier 5.4). Until lot 9 the
rule subtracted nothing and concluded nothing when a record lacked its ID. Neither the Scan nor a Dedup report
holds a count per column, and Dedup, the Scan and the format of the Dedup report are not to change for it.

## Decision

- A copy repeats the whole row, so the presence of the ID is the same in all of its copies. `E_missing`, the
  copies of the rows without an ID, is counted on those rows alone, and `E_present = E - E_missing`;
  `R_residual = (P - E_present) - D`. `E` is the exact total of any source (Scan, Dedup report, Deep count).
- A **light mode** of the engine of Dedup, `count_missing_id_copies`, keeps a table of the rows that lack a
  value in one of the named columns only, so its memory follows those rows and not the file. It reads the file
  once, on its own, for every identifier column that lacks a value. The full mode (one reading giving `E` and
  `E_missing`, but a table of all the rows) was not retained: it would leave a file of 500,000 to 2,000,000
  records out of the automatic choice, where the light one covers it.
- A new analyzer `missing_id_copies` (not an extension of `duplicate_rows_count`, whose result, version,
  statuses and `already_satisfied` on an exact Scan stay as they are). It is chosen by the planner under the
  criteria of lot 8 and needs an exact total of the copies, known or planned (`copies_unknown`); the
  candidate of the planner widens to an identifier that lacks a value (CSV only), which makes the automatic
  `analytical_distinct` and `duplicate_rows_count` available to such a column. This departs from the letter of
  the cahier 12.1 point 4, written for the V1, where the missing IDs forbade a conclusion.
- A cell has a value when the Scan counted it in `values.count`; the classifier and the null markers of the
  Scan's configuration are replayed, and the count of rows without a value is checked against the Scan.
- The object stays `limited` with the reason `missing_ids`: a record without an ID remains among the distinct
  rows, so no `unique` is ever `true`. The figures are given, `after.unique` is `false` when a repetition remains
  among the rows that have an ID, a new interpretation `unique_among_present_ids` says that none does, and
  `near_unique` stays `null`. The threshold is `U_present >= 2`.

## Consequences

- No change to the Scan, to Dedup or to its report. `rule_version`, the Report `format_revision` (5) and the
  second-pass revision (4) stay: the P0 object and the revisions are unpublished.
- Two readings of a large file when its total `E` is also to count (one full, one light); each is cached
  at its own key.
- The cost constant `NS_PER_CELL["rows_without_id"]` is measured on one profile of data, like the others.
- Rejected: counting per column in the Scan (the first pass is not to change), a new Dedup report member,
  a combined analyzer with two outputs, and a `true` unique for the rows that have an ID.
