# Findings, Overview and labels are views computed at render time

Date: 2026-10-16 (lot R0 of the Report overview work)

Status: superseded on 2026-10-17 by `2026-10-17-report-summary-built-with-the-document.md`
(lot R10b): the members are built with the document, not at render time.

## Context

Errors, Issues and Missing must be quantified, explainable and consistent with
the Scan. The Scan already holds the facts (`observations`, detector coverage,
`missing.components`) and design 18.14 says the pages read them without
recomputing a rule.

## Decision

- Findings are view models (`report_findings.py`) built from `observations`,
  detectors, the classification and `analyses`, never serialized.
- Overview and Details are also computed at render time from the same document
  and the measures already derived (`report_measures.py`, `report_insights.py`).
- A finding carries a code, a class (error, issue, information), a unit, a
  population, a share with its denominator, an accuracy, an evaluation state and
  its basis. Merging two findings needs proven overlap.
- An Error needs an established classification and a deterministic rule; the
  same fact on a candidate classification is an Issue.

## Consequences

- No new JSON member for the table: one source of truth, no stale copy.
- Changing a wording or a rule does not change a document; only the rendering
  changes.
- The meaning of `type_error_count` changes: the table's Error is derived from
  findings.
- Third parties reading only the JSON get the facts and the classification, not
  the qualified findings.
