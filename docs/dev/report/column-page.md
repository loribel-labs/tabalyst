# The column page (lot R13)

Status: mockup validated by the maintainer on 2026-10-18 with the recommendations of
section 9; implemented in `src/tabalyst/report_column_page.py` and `templates/column.html`.
Guiding vision: Simple, Clear, Smart. Differences from the mockup: the Shape block is also drawn for a
text column of any type (lengths and characters), and the "Checked, nothing found" list counts each
check once, the errors and the issues lists sharing their checks. It extends `summary-table.md` 19 (column page, lot R10), 20 (a Report that
renders without computing) and 22 (details of the Findings, lot R12), and replaces 19 where
they differ once the mockup is validated. The page is the one `tabalyst report --details`
writes for each column (`templates/column.html`).

The mockup is in `D:\GIT.test\tabalyst\artifacts\r13\mockup\` (outside the checkout, rule of
`AGENTS.md`): three static pages of the demo `insurance-customers` (`code_postal`,
`date_naissance`, `prime_annuelle`), generated from its real `report.json` and the real words of
`report_labels`, with `column-page.css` as the only new style. No production code changes
before the mockup is validated.

## 1. What is wrong with the page today

R10 added the exposure and two cards; the page was never designed. Read on `date_naissance`:

- The same figures are printed four times: the date formats in "Detected formats", "Date formats",
  the date "Breakdown" and the date "Formats"; the variants in Findings and in Transformations; the
  Errors and Issues cards repeat the Observations card.
- Twelve sections of the same weight, in the order the code grew, with no question answered first:
  is something wrong, what, how sure, and what are the values.
- The findings are a title and a count. The details R12 built (formats of ambiguous dates, minority
  lengths, whitespace marks, groups of variants) are visible only in the hover of the Findings table.
- Raw dumps are printed (the JSON `details` of a detector, the ids of observations), and the
  accuracy words (exact, at least, sample) are explained nowhere on the page.
- Layout: five metric tiles in a row, cards of unequal height, no verdict near the title, no way to
  go to the next column.

## 2. Principles

1. **One question per block, in the order a reader asks them**: what is this column, what is wrong
   with it, what are its values, what shape do they take, what is not established, where is the raw
   evidence.
2. **A figure appears once.** Where two members hold the same figure, one block prints it and the
   other links to it.
3. **Findings are the heart of the page.** Each Error and Issue is a card with its nature, count,
   accuracy, limit, examples and its R12 detail written in full, not in a hover.
4. **No computation at render** (20). The page reads stored members and writes words from codes and
   numbers through `report_labels`. Where a block still reads a render-time view of the Scan (6.2
   below), the contract says so and the view stays unchanged.
5. **No new component, no new colour.** Panels, metrics, cards, accuracy marks and statuses of
   `theme.css`; new rules are listed in 7.
6. **A state is never carried by colour alone.** Every status has a word and a shape (a filled or
   hollow dot, a mark in the accuracy chip).
7. **No report option and no new JSON member** (maintainer decision, lot R13). The page is a new
   reading of the existing document.

## 3. Page layout

```text
Header   name, path, position, rows        [prev] [next] [Full report]
Strip    family / type   one-sentence profile   [errors] [issues] [exposure]
 01 Summary          the figures, the interpretation of the type
 02 Findings         Errors, Issues, Remarks, what was checked and found nothing
 03 Values           the stored values with their exact counts
 04 Text|Dates|Numbers|Distribution   what the second pass and the Scan say of the shape
 05 Formats and patterns   the formats once, detectors and patterns folded
 06 Cleaning         normalization stages
 07 Limits           what the Scan could not establish, accuracy legend
 08 Scan evidence    facts of the field, every group folded
 09 Data sample      rows of the sample, this column only
```

Side bar groups: Read (01 to 04), Understand (05 to 07), Evidence (08, 09), Navigation (Full
report). The count beside Findings is the number of Errors and Issues and is the attention colour
when it is not zero. Under 860 px the side bar is the existing sticky strip of tabs, with 44 px
targets.

A block that has nothing to show is not drawn (no 04 for an enum with no insight, no 09 when the
document holds no row sample), except Findings, which says that nothing was found, and Limits,
which says that no measure was limited: an absence of problem is information.

## 4. Blocks: content, order and source

Source column: **Report** is a member built with the document (20); **Scan** is a fact of the
Scan kept in the document (`datasets[].fields`, which the Report keeps); **view** is a presentation
view over stored facts that `report_views` builds when the document is loaded (existing code, no
rule, see 6.2).

### 4.1 Header and strip

| Part | Content | Source |
| --- | --- | --- |
| Title row | name, `Column N of M`, path, number of rows, Full report | `ColumnProfile`, dataset summary |
| Neighbours | previous and next column pages, by name | order of `dataset.columns` and the page links `generate_reports` already knows; absent for a report whose pages are not all written |
| Family and type | family title and type label, the family dot colour of the Summary table | `classification` (`FAMILY_LABELS`, `type_label`) |
| Sentence | the profile of the column | `summary.overview` through `overview_sentence` |
| State chips | `No error detected` or `N kinds of error`; `N kinds of issue`; `Values masked` or `Values hidden` for that exposure | `summary.findings` lists, `column.exposure`; the first two are links to 02 |

### 4.2 01 Summary

- Four metrics: Analyzable values, Missing (percentage and, when not zero, its components absent,
  null, empty, blank, marker), Distinct (value and accuracy mark), Findings (errors, issues, remarks).
  Source: `field.values.count`, `summary.findings.missing`, `column.distinct`, the three lists.
- Interpretation card: type with `state` and `basis`, technical type with its confidence (never
  a classification percentage), traits, alternatives, evidence (ids and roles), exposure. Source:
  `classification`, `type_confidence`.
- Type counts card: the technical types counted and the native types of the source. Source:
  `type_counts`, `field.native_types`.

### 4.3 02 Findings

One card per Error then per Issue, in the order of `summary.findings`, then Remarks.

| Part of the card | Content | Source |
| --- | --- | --- |
| Head | `Error` or `Issue` in the class colour, the label with its count (`finding_text`), the share or population on the right | `Finding`, `preview_of` |
| Left list | What it is, Counted in, Accuracy (word and explanation), each Limit, the Examples (chips, whitespace visible) or the reason there is none | `FindingPreview` |
| Right: the detail | the R12 detail in full: `dates`, `patterns`, `lengths`, `whitespace`, `types` as the sections of `FindingDetailView`, `variants` as groups (the first six, the rest in a folded group) | `summary.finding_details` through `finding_detail_views` |

- **Which detail goes with which finding.** The page takes the first entry of `Finding.basis` that
  is the id of an observation of the column and reads the detail by `(column id, observation rule)`,
  the key the Findings table uses. `report_table.page_findings` returns it with the preview (a
  view model, never serialized); the template does no lookup. A finding whose basis is not an
  observation (`type.outside_family` has `technical_type`) has no detail and says so in 02 with the
  reason (the Scan keeps no value for it).
- **Remarks** are the informational observations of the column not already told by a finding
  (missing values, constant or empty column), each on one line with its count and accuracy. The
  whitespace observations are informational yet back the whitespace Issue, so they are not
  listed twice.
- **Checked, nothing found**: one folded group, the checks of both lists whose state is "none
  detected" (`check_lines`), with how many values each covered. The checks that did not run, or
  ran partially, are written as findings caveats in the card they qualify and in this group.
- A column with an exposure `mask` or `hide` follows 22.4: the details hold masks or nothing and say
  so; the card never prints a raw value.

### 4.4 03 Values

- The first line says what the list is: all the distinct values, or `N of the M distinct values the
  Scan stored (a diverse or random sample out of K)`; every count is exact.
- One line per value: the value, a bar proportional to the largest count listed (a drawing, not a
  figure), the count. A value the Scan cut is marked. Masked values are merged masks; a hidden
  column says why the list is empty.
- A folded group holds the measures of the Details column (`summary.details.measures`: share
  recognized by the detector, formats, keys).
- Source: `summary.values`, `summary.details`.

### 4.5 04 Shape (Numbers, Dates, Text or Distribution)

One block, titled by the type, in place of the Numeric, Dates, Text and Insights sections.

| Type | First row (metrics) | Then |
| --- | --- | --- |
| Number | minimum, maximum, mean, median (and range) | insight cards |
| Date | valid, ambiguous, invalid dates, other values | insight cards (parts of the dates, distribution over time) |
| Text | shortest, longest, mean and median length | insight cards, then the character map |
| Other | none | insight cards, when there are some |

Source: `view` (`numeric`, `date_profile`, `string_profile`, `characters`, `insights`; see 6.2). The
accuracy of each figure is written by its card, as today.

### 4.6 05 Formats and patterns

- **Formats**: one table, `Format | Read as | Values | Share`. A date column lists the formats of
  the date profile with their day-month order; any other column lists the formats the detectors
  recognized with the detector's name. Each format appears once (it appeared four times).
- **Detectors**: folded, one card per detector (status, eligible, matched, ambiguous, invalid) and the
  examples by outcome through `exposed_evidence`. The raw `details` JSON is no longer printed (it stays
  in `report.json`).
- **Patterns**: folded, the family tree of today with its legend and its accuracy line. A column
  with no pattern says why in one line.
- Source: `view` (`date_profile.formats`, `detectors`, `patterns`).

### 4.7 06 Cleaning

The normalization stages as one table (`Stage | Values changed | Distinct after`) with the stages that
changed something in the attention colour, then one line that points to the variants in 02.
Source: `column.normalization`. The list of variant groups is no longer printed here.

### 4.8 07 Limits

- The limited measures of the column (label, measure, reason, setting, limit, lower bound) and the
  diagnostics of its path, one list each. Source: `column.limits`, dataset diagnostics.
- The accuracy legend, once: exact, at least, sample, estimated, not computed, with the words of
  `acc_titles`.

### 4.9 08 Scan evidence

Facts of the field kept in the document, each group folded and closed: presence and missing, first
and last values, string categories and characteristics (with the length histogram), numeric
statistics, boolean counts, temporal range. Nothing is added; the groups of today are reordered and
folded. Source: Scan (`column.field`).

### 4.10 09 Data sample

The rows of the row sample for this column only, as today (original row numbers, origin of the row,
value or `hidden`, `empty`, `absent`). Source: `ds.rows`.

## 5. What is removed or moved

| Today | Becomes |
| --- | --- |
| "Detected formats", "Date formats", date "Breakdown" and "Formats" (4 prints) | one Formats table (4.6); the breakdown by outcome is the dates detail of 02 |
| "Observations" and "Errors"/"Issues" cards | merged in 02 |
| "Value coverage" card | the first line of 03 |
| "Type counts", "Native types" | Summary (4.2) |
| "Detector details" JSON dump | removed from the page |
| "Variant groups" of Transformations | the variants detail of 02 |
| "Insights" section at the end | inside 04 |
| "Limits" with the diagnostics under Observations | 07 |

## 6. What the page reads, and what it does not compute

### 6.1 Rules

- `summary.findings`, `overview`, `details`, `values` and `finding_details` are read as they are.
- Words come from `report_labels` by code and parameters. New templates (neighbour links, the
  first line of Values, group titles) are added there, English only (20.7).
- The exposure was applied at the build (20.2): the page has no gate. Tests for a raw document
  forced to `mask` or `hide` stay (`test_report_column_page.py`).
- No page-side sort, filter or sum. A bar width is a ratio of two stored counts, the one
  arithmetic of the page; no figure is derived from it.

### 6.2 Render-time views that remain (decision requested)

`numeric`, `date_profile`, `string_profile`, `distinct`, `patterns`, `characters`, `quality`,
`limits` and `insights` of `ColumnView` are built when the document is loaded, from `fields`,
`derived` and `analyses`, as 20.5 left them. They hold no rule that decides a finding but they are
a computation at render. Proposal: R13 keeps them unchanged and reads them as above; moving them
to members built with the document is a separate lot (R14), after which `fields` could be
pruned (20.5). The page does not depend on the choice: it would read `summary.shape`,
`summary.formats` instead.

## 7. Style, accessibility, sizes

- New classes only (the mockup's `column-page.css`): the verdict strip and its state chips,
  `fnd` (finding card) with `fd-*` (detail lists) and `vgroup`, `dsc` (a folded group, a native
  `details` element), `vbars`, `ftab`, `legend`, `srows`. Tokens only: `--err`, `--issue`, `--ok`,
  `--fam-*`, `--line`, `--text*`; both themes follow from them.
- Keyboard: skip link, one `h1`, `h2` per block, `h3` per finding, `h4` per detail; disclosures are
  native `details`/`summary` (Enter and Space), no script. Focus order is the reading order; the
  neighbour links come right after the title.
- Touch and small screens: targets at least 24 px (44 px for tabs and disclosure heads), the card
  columns stack under 1180 px, the bars stack their line under 720 px, no horizontal scroll of the
  page at 390, 720 (200 % zoom), 820 and 1440 px.
- Whitespace in values is shown with the marks of 22.6 and their spoken equivalent; values are
  escaped (RT-14).
- Print: disclosures stay as the reader left them, the strip and the cards do not break across
  pages, the side bar and the neighbour links are hidden. A script opens the folded groups before
  printing (`beforeprint`), so the paper holds the evidence.
- Two themes, tested: the contrast of the class colours is the one of the Findings table.

## 8. Tests

- `tests/scan/test_report_column_page.py`: the existing tests stay (exposure, public signatures);
  new tests: the blocks and their order; the absence rules of 3 (no 04, no 09, Findings with
  nothing found); one card per Error and Issue with its detail (parity with the member: the
  detail the page prints is `finding_details`, byte for byte through the same words); a format
  printed once; the neighbour links; a finding with no example says so; no JSON dump of a detector.
- The "no computation" guard of 20.4 covers the new view (`page_findings`).
- `tests/browser/report.cjs` extended to a column page: four sizes, two themes, no horizontal
  scroll, the disclosures open from the keyboard, the skip link, the sticky tabs under 860 px, a
  finding card with and without a detail.
- Documentation: `docs/en/report/read-report.md` (a "Column page" section, the blocks in order, how
  to read a finding card), the demos regenerated (`examples/tools/regenerate.py --fresh`, check on
  `insurance-customers`). Follow-up for `tabalyst-studio`: a new capture of the column page.

## 9. Decisions of the maintainer (2026-10-18, on the mockup)

1. **Order.** Summary, Findings, Values, Shape first; Formats, Cleaning, Limits next; evidence
   last. Findings stays at 02.
2. **Values and "Most repeated values".** Both are kept in R13. Letting the insight replace the
   list when it exists is a later question.
3. **Render-time views (6.2).** Kept unchanged in R13; building them with the document is the
   separate lot R14.
4. **Neighbour links.** Previous and next column in the header, only for a report whose pages
   exist.
5. **Detector JSON.** No longer printed on the page.
6. **Dates metrics and dates detail.** The overlap stays (the metrics also give the valid and
   invalid dates).
7. **Folding.** Detectors, Patterns and Scan evidence closed by default; Formats and the finding
   details open. The folded groups open for printing.
