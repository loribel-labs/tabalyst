# Vocabulary of evaluation states

Date: 2026-10-16 (lot R0 of the Report overview work)

## Context

A dash in Errors or Issues could mean zero proven, never checked, or failed. A
detector that tests 100 of 1,000 eligible values and finds nothing is not a
proof for the column (RF-22, RF-23, O-12).

## Decision

Five states, with fixed visible labels: `None detected` (complete check, nothing
found), `Not assessed` (disabled or never run), `Partially assessed` (adaptive
or limited coverage), `Not applicable`, `Assessment failed`. The dash is not
used in Errors and Issues. The mapping from detector and measure states is in
`docs/dev/report/summary-table.md` section 6.4.

## Consequences

- `None detected` is only shown after a complete check.
- A technical `failed` is never counted as an invalid value.
- Labels live in `report_labels.py` and may be reworded later; the state codes
  do not change.

## Amendment (2026-10-17, lot R9a)

The maintainer asked that an Errors cell whose state is `Not applicable` show a dash
(`-`) instead of the words: 21 of the 34 columns of the demo have no deterministic
rule and the repeated words weigh on the table. The word stays in the filter, in the
tooltip and as a visually hidden text, so the state is still told to a screen reader
and the dash cannot be mistaken for zero (`None detected`) or a failure. Issues keep
their words.

