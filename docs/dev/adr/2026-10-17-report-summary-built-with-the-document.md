# The Report document holds the qualified findings and the exposed values

Date: 2026-10-17 (lot R10b of the Report overview work)

## Context

Lot R0 decided that findings, Overview and Details are views computed when the HTML
is rendered, from a Report that carries the Scan base (ADR
`2026-10-16-findings-computed-at-render`). Lots R4 to R10 followed it. Cost: the
HTML recomputes `column_findings`, `overview_for`, `details_for`, `finding_preview`,
Signals and quality from raw values, the exposure gate is applied at every reading
(and was missed twice: the Numeric table and the column page), the sentences are
English composed in Python, and `report.json` is 4.9 MB for 34 columns, most of it
what no page reads.

## Decision

- The Report document carries, per column and per dataset, the qualified findings,
  the Overview and Details facts, the signals and the quality groups, as codes,
  numbers, units, accuracy and states, without a sentence.
- The exposure is applied once, when the document is built. A column exposed as
  `mask` or `hide` has no raw value in the document.
- The rules stay in the same modules; they run at build time, once per column.
- Words are templates per language in `report_labels.py`, looked up by code and
  parameters at render time.
- The Report no longer promises to contain the Scan. What leaves is measured, then
  recorded in the contract (section 20.5); what Explore and the loaders read stays
  until their contract is amended.

## Consequences

- Third parties reading the JSON get the qualified findings, not only the facts
  (reverses a consequence of the earlier ADR).
- A change of rule or word that alters a member changes the document; a change of
  wording alone still changes only the rendering.
- One computation per column: the Summary, Findings, previews and column page cannot
  disagree.
- `report --scan` builds the same members in memory; the renderer has one path.
- Report revision 4 is still unpublished: no revision bump, changelog entry only.
