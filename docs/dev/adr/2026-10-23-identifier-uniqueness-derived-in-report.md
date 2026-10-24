# Identifier uniqueness is derived in the Report, from facts it already holds

Date: 2026-10-23 (lot 0 of the Unique ID plan)

## Context

An identifier column repeats its values when whole rows are copied. `identifier/unique_id` in
the Scan means unique in the raw population, and `identifier.repetition` counts `P - D`. Neither
tells a user whether the repetitions come from exact row copies or from distinct records sharing an
ID. The facts to tell exist: the Scan holds `D` (`values.cardinality`) and the count of copied
rows (`records.duplicates`), and Tabalyst Dedup writes an exact `<stem>.dedup.json`. The Scan must
stay fast and its classification must not change (UID-001, UID-010).

## Decision

- The qualification is a pure, versioned function of facts (`rule_version: 1`) that the Report
  evaluates when it builds the column summary, in the member `identifier_uniqueness` of
  `ColumnSummary`. It follows the ADR `2026-10-17-report-summary-built-with-the-document`: JSON and
  HTML read one stored value, and words are looked up by code in `report_labels.py`.
- The Scan, its classification and `identifier.repetition` do not change. The decomposition lives in
  the new object.
- `E` (copied rows) comes from the Scan's exact count first, then from a validated Dedup report.
  Disagreement between exact sources is a `failed` evaluation with a stable reason, never a silent
  choice. A refused proof is a diagnostic in the object, never an error of the Report.
- A Dedup report is supplied by `report --dedup-report <file or folder>` (API and configuration
  aligned), or found only as the `<stem>.dedup.json` beside the source. Nothing runs Dedup, reads a
  CSV output or searches folders.
- Row identities are interchangeable for a CSV: verified by cross tests (A1), the Scan's digest
  and Dedup's `full_decoded_csv_row_v1` give the same count wherever both accept the file.
- Report `format_revision` becomes 5 (format 0.2.0 unchanged). Threshold: `U >= 2` for any
  conclusion after deduplication. No near-unique threshold in P0.
- P1 may add a count-only mode of the Dedup engine and an exact analytical cardinality analysis; they
  would feed the same inputs without changing the object.

## Consequences

- The standard Scan path is untouched; a Report with exact Scan facts needs no new reading.
- A user with a limited or disabled duplicate count gets `not_assessed` or `limited` until a Dedup
  report is given, instead of an invented figure.
- The Report JSON grows by one small object per identifier column; consumers get codes, counts and
  provenance, no sentence.
- `rule_version` and the Report revision move together with any change of formula or reason.
- The contract is `docs/dev/report/identifier-uniqueness.md`; a change to it is a change of this
  decision when it touches the points above.
