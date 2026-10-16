# The classification is persisted in the Scan and refined in the Report

Date: 2026-10-16 (lot R0 of the Report overview work)

## Context

The Columns table needs a family and a type per column. The Scan already holds
`interpretations` (detectors that reach a minimum share) and a technical type,
and the Report computes a `semantic_type` from them at build time. The
classification must be shared by Scan, `scan --deep` and Report (decision D-11),
usable without the source, and reproducible (RT-11).

## Decision

- The first-pass classification is a block of the Scan, `fields[].classification`,
  computed by `scanner/classify/` from the blocks of the field.
- The Report carries the final classification in `columns[].classification`,
  refined from `analyses.deep` by a pure function when the second pass supplies
  a fact the first pass lacked (for example an exact distinct count).
- It replaces `ColumnProfile.semantic_type` and `DatasetSummary.semantic_type_*`.
  The technical type and `interpretations` stay.
- Findings, Overview, Details and labels are not persisted (see the findings ADR).
- The four Text length bounds live in `scan.classification`, since the type they
  decide is persisted in the Scan.

## Consequences

- The classification joins revision 4 of the Scan and of the Report, which is
  still in preparation (rule P3: one revision per published version; the last
  tag ships revision 3). The break is accepted in beta and recorded in both
  changelogs.
- Changing a Text bound changes `config_sha256` and requires a new scan.
- A Report rendered from a Scan or a Report document gives the same
  classification without reading the source.
- `Classification.rule_version` lets `engine_warning` tell that a document was
  classified by other rules.
