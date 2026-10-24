---
title: Read a Tabalyst Report
description: Read each table and indicator in a Tabalyst Report, including its purpose, columns and limits.
---

**Tabalyst Report** analyzes one dataset and creates an interactive HTML report
and a [JSON profile](json-profile.md). This guide follows the HTML sections in
display order. Use [Types and patterns](../reference/types-and-patterns/index.md) for
the complete list of inferred types, semantic types and detectors.

```console
tabalyst report customers.csv
```

A dataset is the rows of a CSV file, one selected JSON collection, the object
lines of a JSONL file, or one selected Excel sheet or named table. In JSON, a
column is usually a scalar field path such as `address.city`. Section counts
refer to this dataset. The optional numeric, date, string, detector, pattern and
limits sections appear only when they have results to show.

## How counts are qualified

Every figure that could be misread says what it counts. Each label is a word
with a shape in front of it, never only a color:

| Label | Meaning |
| --- | --- |
| exact | Counted on every value of the file. |
| `≥` or at least | A scan limit stopped the count: the real figure is at least this. |
| `≈` or estimated | Estimated from a sample of the values, shown with its error. |
| sample | Counted on a sample of the distinct values, not on the whole file. |
| not computed | The scan did not compute it, for example when `scan.observations.enabled` is `false`, or the second pass did not run the analysis. |

A figure without a label is exact. An integer is always written with all its
digits, however large.

## Dataset overview

**Purpose:** establish the size and completeness of the dataset before
investigating individual fields.

| Indicator | What it measures | What to check |
| --- | --- | --- |
| Rows | Records analyzed, excluding a CSV or Excel header. The note counts empty rows. | Compare with the expected source size. Excluded malformed records appear as a separate quality observation. |
| Columns | Fields analyzed. The note counts cell positions: rows × columns for a table; field occurrences plus absent positions under parent objects for JSON. | Check whether the expected fields were found. |
| Missing cells | Missing positions divided by all analyzed cell positions, with the count below. Empty or whitespace-only values, configured markers and absent JSON members can count as missing. | Check the affected columns and the effective missing-value rules. |
| Duplicate rows | Records equal to an earlier record by exact raw values across columns, excluding the first occurrence. | `≥` is a lower bound after the tracking limit; `–` means the check was disabled. |

Three cards sum what the checks found and how far they went. They add up the
findings of the [column summary](#column-summary), column by column, and never
guess: a sum only joins findings of one kind counted in one unit, so no card adds up
Errors of different kinds. Every figure that stands for columns opens a popover (click,
Enter or Space; Escape closes it and gives the focus back) with the columns behind it.

- **Finding types** (the card with the notched corner) gives two figures: the **Error
  types** and the **Issue types**. A type is one kind of finding in one column (an
  invalid email value in `email` is one Error type), so the figures count kinds of
  problem, never values; each figure sits in a framed tile and the number of columns
  ("21 of 34 columns") is underneath (a column with both
  counts in both). Under them, every **affected column** with its widest finding: the
  share of the column's values that this finding touches, as a number and as a bar
  on a log scale (so that 0.01% and 10% stay readable), the class and name of that
  finding, and how many other types the column has (hovering the row lists all of them, with their counts). A line under the bars says what the bar is, and its `i` button says that the scale is logarithmic. Columns are ordered by that share;
  one with only findings without a share (spelling variants) comes last. The shares
  of two findings are never added. The names link to the row of the column in the summary. At least eight columns are
  listed, more when the height of Column types allows it, and the button
  "+ N more" opens all of them. The figures open the columns with their findings.
- **Errors and Issues** lists the kinds of finding present, Errors first and then
  Issues, each ordered by the columns touched. A row has a dot of its class before
  the title, the title, the sum of the finding
  over the columns that have it, a thin bar of that share on the same log scale as the columns of the first card, and a line with the class in words (so the colour is never the only cue), its unit, its share when it is
  known (two decimals, three for a very small one, `<0.001%` below), and the number of columns. The share is the sum out of every value the check
  looked at, in all the columns it covered, and is left out when the finding has no
  population (groups of spelling variants). `≥` marks a sum with a lower bound. A row
  opens a short sentence on what the finding is, then the columns with their figure and, by case, their details: the largest group
  of spelling variants of each column, or the note that Tabalyst does not guess the
  order of an ambiguous date. At least eight kinds are shown, more when Column types is taller, so that the three
  blocks end together; the others are in the Findings section (the line "+ N more"). A defect
  by the structure of the source (excluded records, blank or repeated column names)
  is listed after them as a *Dataset* row. A line says how many columns the checks
  did not completely cover, so that a zero is not read as a guarantee. Without any
  finding the card says that no Error and no Issue was detected.
- **Column types** counts columns twice, not cells: by family and type of the
  classification, then by technical type.

### Kinds of finding in the overview

Twelve kinds of finding have a row. The title and the line that says what it counts are
the ones below; the figure is the sum of the finding over the columns that have it, counted in
one unit.

| Kind | Class | What it counts | Counted in | Where it comes from |
| --- | --- | --- | --- | --- |
| Invalid dates | Error | Dates that do not exist in the calendar | values | The date detector, on a column established as dates |
| Invalid values | Error | Values failing a validation check | values | The email, phone, postal code, URL, IP address and UUID detectors |
| Type mismatches | Error | Values outside the inferred column type | values | A column typed Integer or Number |
| Ambiguous dates | Issue | Values matching multiple date orders | values | Dates that read as day-month or month-day; the order is never guessed |
| Ambiguous numbers | Issue | Values that read in more than one way | values | The number detector (decimal comma or point) |
| Spelling variants | Issue | Groups of different spellings | groups | Values that differ only by case, accents or spaces |
| Minority patterns | Issue | Distinct values in less-common patterns | distinct values | The patterns of a column |
| Minority lengths | Issue | Values with less-common lengths | values | The string lengths of a column |
| Mixed types | Issue | Values outside the closest type | values | A column whose values fit more than one type |
| ID repetitions | Issue | Repetitions beyond the first occurrence | values | An identifier whose distinct count is exact. The count is raw; the [column page](#column-page) separates the repetitions that copied rows explain |
| Surrounding whitespace | Issue | Values with leading or trailing whitespace | values | The scan observation of trimmed cells |
| Repeated whitespace | Issue | Values with repeated whitespace | values | The scan observation of collapsed whitespace |

The class is written before the title, so the colour is never the only cue. Tabalyst
has two classes of finding to act on, Error and Issue; it has no Warning class.

Two information findings, an empty column and a constant column, have no row: a
finding points at what to look at, and these say what a column is. They are in the
Overview of the column.

The overview, the column summary and the findings answer different questions: how
much and how far, which column, and what exactly. See
[Findings](json-profile.md#findings) and the
[Findings catalog](findings.md), which lists every finding code.

## Observations

**Purpose:** list what the scan found, rule by rule, with its status, the
column concerned, the count and what it is out of. A count is exact unless its
accuracy says otherwise: *at least* when a limit stopped it, *sample* when it
was made on a sample of the distinct values.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Status | Confirmed issue, candidate anomaly or remark. | Missing values and constant columns are remarks, not issues. |
| Finding, Column | The rule and the column it concerns; a finding about the dataset has no column. | Filter by status to start with the issues. |
| Count, Out of | What was found, out of what: values, records, distinct values or columns. | Do not compare counts of different populations. |
| Accuracy | exact, at least or sample. | An *at least* count is a proven minimum, not an estimate. |
| Detail | The first record numbers, the patterns and the limits behind the finding. For spelling variants, the largest groups with their spellings and counts, the most frequent first. For ambiguous dates, the pairs of formats that fit the same values (for example `DD/MM/YYYY or MM/DD/YYYY`) with their counts, the unambiguous values of the column by day-month order and the formats it holds without doubt. For minority patterns, the dominant pattern and the rare ones with their distinct values and up to three example values each, taken from a sample. For minority lengths, the dominant length and the others with their counts and shares and up to three example texts each, read from the cases the scan kept for each length (lengths count the characters of the text after normalization, so an example is shown trimmed and with its whitespace collapsed). For surrounding and repeated whitespace, the number of cells of each kind (before the text, after it, repeated inside it) and up to three example texts of each, read from the cases the scan kept, with the whitespace made visible by marks (a dot for a space, an arrow for a tab, a return mark for a line break). For mixed types, the share of each technical type the scan recognized in the column and the type it comes closest to; no example is listed. | Use the record numbers to find the rows in the source. In a group of variants, the most frequent spelling is the likely target of a correction; the others are the candidates to review. For dates, the unambiguous values by order show which reading the column leans to; Tabalyst never picks one, so set `scan.detectors.date.ambiguous_order` once you know. The examples of a pattern are a sample: a pattern can show none, and that says nothing about the others. A masked column shows merged masks, a hidden one nothing; the formats of dates are shapes, not values, and stay. A masked or hidden column has no pattern detail at all, and its length and whitespace examples are masked or absent. The examples of whitespace and of lengths do not depend on the sample of distinct values: the scan keeps a few texts of each case with their exact counts, so two cells out of 100,000 are listed. The hover says when it lists every distinct text of a case and when it lists a selection of them. |

The table shows 25 findings at a time and up to 500; the JSON profile lists
them all. Without observations (`scan.observations.enabled` is `false`) the
section says that they are not computed.

## Column summary

**Purpose:** read each field in one row: its classification, a factual sentence
about it, its completeness and its findings. The classic **Columns** table, with
the technical type, sits right after it. Each row is one field, identified by its dataset and
its field `id`, never by its name alone. **With errors** keeps the fields with an Error; **Quality issues** filters to fields
with an Error or an Issue in the table; **With observations** keeps the fields
the scan has an observation about, remarks included.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Column | Name and source position. JSON paths identify nested fields; names in a table may be blank or repeated. | Use position, the path under the name or the JSON profile's stable `id` when a name is ambiguous. |
| Type family | The family of the [classification](../scan/format.md#classification): `Identifier`, `Categorical`, `Numeric`, `Temporal`, `Contact`, `Geographic`, `Web / Network`, `Text` or `Other`. | Filter and sort here to see every field of a family; the filter is independent of **Type**. |
| Type | The type inside the family, such as `Unique ID`, `Enum`, `Email` or `Short` (a `Text` length). | An identifier type is a candidate that rests on a name and the values; the JSON profile gives the `state` and the `evidence` of every type. See [Types](../reference/types-and-patterns/types.md#classification). |
| Overview | One factual sentence about the field: distinct values, range, recognized formats, median length. | It states no business meaning and never repeats an Error or an Issue. `at least` marks a figure that is a lower bound. |
| Missing | Missing positions as a count and percentage of this field's positions. Absent JSON members count in the denominator. | A missing value is never an Error or an Issue by itself. Check the missing markers in **Analysis settings**. |
| Errors | Values a deterministic rule proves invalid, such as an impossible date or a malformed email, in a field whose type is established. | Each label gives its count in its own unit and opens its preview. `None detected` means the checks ran everywhere; a dash (`-`) means `Not applicable`: no rule exists for this type. |
| Issues | Ambiguities and deviations to inspect, such as ambiguous dates, spelling variants or a minority length. | A rare value is not an invalid one. Under a list, a button such as `1 check partially assessed` opens the checks that did not cover every value. |
| Details | A few values of the field on two lines at most. The hover (or focus, or a tap) holds the whole story: the values with their counts and shares, every Error and Issue label of the column, the groups of spelling variants with their spellings (the most frequent first) and the complementary measures. | A list can be complete or bounded. Sensitive values can be masked or hidden. |

The states of Errors and Issues are written: `None detected`, `Not assessed`,
`Partially assessed`, `Not applicable` and `Assessment failed`. The only dash is
the `Not applicable` of an Errors cell, which keeps its word in the filter and for
a screen reader. Two labels are shown in a cell, then `+N more`. The technical
type of the field (`inferred_type`) is not a column of this table; it stays in
the **Columns** table, in the JSON profile and on the column page.

### Previews of Errors and Issues

Each label of the Errors and Issues cells is a button. Click it, or focus it and
press `Enter` or `Space`, to open the preview of that finding; `+N more` opens the
previews of the other findings of the cell. A state without finding, such as
`Partially assessed`, opens the list of the checks behind it, with what each one
covered or why it did not run. The preview is also the way to read a finding on a
touch screen: nothing depends on hover.

A preview states, when the Scan knows it:

| Line | Meaning |
| --- | --- |
| What it is | The kind of value the finding counts, as a fact and never as a verdict. |
| Counted in | The unit of the count: occurrences, groups, distinct values, positions. |
| Count | The number, written `at least` when it is a lower bound. |
| Out of | The population the count is taken from, such as `100,000 eligible values`. |
| Share | The percentage with its numerator and its denominator. A share below 0.01 % is written `<0.01%`, never `0%`. |
| Accuracy | `Exact`, `At least` (a limit or a partial check stopped the count), `Sample` or `Estimate`. |
| Examples | At most two values the finding rests on. They go through the exposure of the column: masked values are marked, hidden values are not listed. Findings for which the Scan keeps no value (values outside a number type, minority lengths, whitespace) list none. |
| Limit | What the reading does not say, for example that an ambiguous date is not wrong. An Error counted as an Issue because the type of the column is not established says so. |

`Escape`, the **Close** button, a click or tap outside, or `Tab` past either end of
the preview closes it and gives the focus back to the button that opened it. On a
screen narrower than 640 px the preview opens as a sheet at the bottom of the
screen. Errors and Issues carry different marks (a diamond and a triangle) as well
as different colours, and the hidden text of each label starts with the class
(`Error:` or `Issue:`). Tabalyst aims at WCAG 2.2 AA for these controls without
claiming a certification.

## Columns

**Purpose:** locate fields that need investigation and compare their value
shape, detected meaning and completeness. Each row is one field. **Quality
issues** filters to fields with a confirmed issue or a candidate anomaly, such
as a `mixed` inferred type or ambiguous dates; **With observations** adds the
fields that only have remarks, such as missing values.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Column | Name and source position. JSON paths identify nested fields; names in a table may be blank or repeated. | Use position or the JSON profile's stable `id` when a name is ambiguous. |
| Missing | Missing positions as a count and percentage of this field's positions. Absent JSON members count in the denominator. | Check whether the missing markers in **Analysis settings** match your data. |
| Distinct | Different present values after analytical normalization (Unicode composition, trim and whitespace collapse when enabled). | Exact unless marked. `≥ 51` is a proven minimum after a scan limit, with its estimate below it when the scan made one (`≈ 2,031 est.`); `limited` means counting stopped and proved nothing. |
| Inferred type | Value family inferred from present values, such as `number`, `date` or `mixed`. | A `mixed` field did not meet the configured confidence threshold. See [all inferred types](../reference/types-and-patterns/types.md#inferred-types). |
| Type | The type of the column in the [classification](../scan/format.md#classification), such as `Unique ID`, `Enum`, `Email` or `Text / Short`. | An identifier type is a candidate that rests on a name and the values, and the JSON profile gives the `state` and the `evidence` of every type. See [Types](../reference/types-and-patterns/types.md#classification). |
| Error | Count and percentage of present values outside the inferred type. | This is type disagreement, not malformed records or detector failures. It is unavailable for `mixed`. |
| Issues | Confirmed issues and candidate anomalies about this field, with the number of remarks below. | Open the column page or **Observations** for the detail. |
| Examples | A few retained values; the tooltip gives more values and counts. | A distribution can be complete or a bounded sample. Sensitive values can be masked or hidden. |

Missing values do not lower type confidence. For example, `not available` can
disagree with a numeric type if it was not configured as a missing marker. An
email field can have inferred type `text` and type `Email`: these
answer different questions. Add `--details` to link each column to its own
page with scan evidence and value counts:

```console
tabalyst report customers.csv --details
```

## Column page

**Purpose:** read everything the report knows about one column, in the order of the
questions you ask: is something wrong, what, how sure is the report, and what do the
values look like. The page is written for each column when you add `--details`, and the
Column and Details cells of the [Summary table](#column-summary) link to it. It reads the
report document and computes nothing of its own: a figure here is the figure of the tables.

The header names the column, its position and its path, and links the **previous** and
**next** column pages. A strip under the title gives the family and the type, one sentence
that profiles the column, and the number of kinds of error and of issue (each opens the
Findings block). A column whose values are masked or hidden says so there.

| Block | What it shows | What to check |
| --- | --- | --- |
| 01 Summary | Analyzable values, Missing (with what counts as missing), Distinct and the number of findings; the Interpretation of the type (state, basis, traits, alternatives, evidence, technical type and its confidence) and the types counted. An identifier column also has the card *Identifier uniqueness* (see below). | The type is a reading of the values, not a promise: check **state** and **basis**. |
| 02 Findings | One card per Error, then per Issue: what it is, what it counts, how sure the count is, its limit, examples, and the detail beside it (see below). Remarks follow, and a folded list says which checks ran and found nothing. | Start here. A count marked *at least* or *sample* is not exact; see [How counts are qualified](#how-counts-are-qualified). |
| 03 Values | The stored values, most frequent first, with their exact counts and a bar that compares them. | A list can be every distinct value or a sample; the first line says which. |
| 04 Shape | The block takes the name of the type: Numbers (range, mean, median), Dates (valid, ambiguous, invalid), Text (lengths, character map) or Distribution. It holds the insight cards of the second pass. | Not drawn when there is nothing to show. |
| 05 Formats and patterns | Every recognized format once, with how it is read and its share. The detectors and the pattern families are folded below. | Open **Detectors** to see the examples by outcome. |
| 06 Cleaning | The normalization stages, with the number of values each one changed. | A stage that changed values is highlighted. The spelling variants are in the Findings. |
| 07 Limits | The measures the scan could not establish for this column, its diagnostics and the meaning of each accuracy mark. | Read it before relying on a figure marked *at least*. |
| 08 Scan evidence | The facts of the field as the Scan wrote them, in folded groups. | Raw material, for checking a figure. |
| 09 Data sample | The rows of the sample, for this column only, with their original row numbers. | The sample is not uniform over the file. |

**Identifier uniqueness.** A column the Scan classifies as an identifier can repeat an ID
because whole rows are copied, not because two different records share it. The card
*Identifier uniqueness* in 01 Summary separates the two, from figures the report already
holds and, when you give one, a [Dedup](../dedup/index.md) report. It never reads the source
again and never runs Dedup. It shows one of five readings:

| Title | When | What it says |
| --- | --- | --- |
| Unique ID | Every ID is distinct across all the source records, none is missing, and the counts are exact. | The ID is unique before any deduplication. |
| Unique after row deduplication | The repetitions are exactly the extra copies of whole rows. | The ID repeats only because rows are copied; no ID conflict remains among the distinct rows. It is not called *Unique ID*, because the raw count still shows the repetitions. |
| ID repetitions | Some repetitions remain between distinct rows. | The figures give the repetitions explained by copies and those that remain. |
| Uniqueness not fully assessed | A needed count is estimated, limited, disabled or missing, or the scan did not cover every record. | No conclusion; the reason is stated. |
| Missing IDs | Some records have no ID. | Uniqueness after deduplication cannot be established. |

The card gives the evidence of each figure (the Scan, the second pass or a Dedup report with
its file name) and the proofs it refused, with the reason. A repetition is an observation of
quality, not an Error: the finding *ID repetitions* stays raw and links to this card. Only a
Dedup report that matches the SHA-256 of the scanned source, is complete and counts the same
records is used; give it with `--dedup-report`, or keep `<name>.dedup.json` beside a CSV
source. The entry *Identifier uniqueness* of [Analysis settings](#analysis-settings) gives
the rule version and the sources actually used. Deciding whether an ID is *nearly* unique, and
counting the copies with a second pass of the report itself, are not available yet.

**A finding card.** The left side states what the finding is and how far to trust it. The
right side holds the detail that explains it: the groups of spelling variants, the formats
that fit the same ambiguous dates with the unambiguous values by day-month order, the
dominant length and the minority ones, the minority patterns, the kinds of whitespace made
visible, or the composition of a mixed column. These are the details of the
[Findings table](#observations), written in full instead of in a hover. A finding for which
the Scan keeps no value (values outside a number type) says so. Examples are a sample and
can be missing for a rare case; a masked column shows merged masks and a hidden one nothing.

The page works with the keyboard and by touch, reads in both themes, and prints with its
folded groups opened.

## JSON structure

**Purpose:** show the paths and containers behind the flattened columns. This
table appears for JSON and JSONL, including objects and arrays that are not
themselves scalar columns.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Path, Depth, Role | Location in each record, number of path segments and structural role. | Follow paths such as `orders[].total` back to their parent array. |
| Native types | JSON types encountered at the path, including containers and `null`. | Find fields that vary in shape between records. |
| Present, Absent | Occurrences and missing members relative to the path's parent. | Distinguish an absent field from an explicit JSON `null`. |
| Array length, Empty arrays | Array-size evidence when the path is an array. | Check whether empty or unusually sized arrays affect the data you expect. |

**Records**, **Paths** and **Maximum depth** summarize the structure above the
table. Field and depth limits appear under **Limits and diagnostics**.

## Transformations and variant groups

**Purpose:** reveal values written in several ways without changing the source
or the raw **Data sample**. Stages run in order: Unicode composition (`nfc`),
trim, internal whitespace collapse, case folding and accent removal.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Unicode composed, Trimmed, Whitespace collapsed | Number and percentage of occurrences changed by each enabled analytical stage. | Compare with the raw values when a stage changes many cells. |
| Case folded, Accents removed | Occurrences changed by the comparison stages. | These stages can group spellings without changing the analytical values. |
| Distinct | Distinct present values after the analytical stages. | Compare with **Compared distinct** to see the effect of comparison. |
| Compared distinct | Distinct keys after all enabled comparison stages. | A smaller count suggests case or accent variants. |
| Variant groups | Groups with at least two raw spellings that share a comparison key. | Open the groups table to inspect the actual spellings. |

In the **Variant groups** table, **Comparison key** is the value used for
comparison, **Occurrences** totals its appearances, **Spellings** counts raw
forms, and **Variants** lists bounded forms with counts. For example,
`Montréal`, `montreal` and `MONTREAL` can group together when the relevant
stages are enabled. A group is an analytical equivalence, not proof of equal
meaning. Counts or lists can be limited; the [normalization fields](json-profile.md#normalization)
record their statuses.

## Numeric analysis

**Purpose:** summarize accepted numeric values in inferred `integer` or
`number` columns. The table appears when numeric statistics are available.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Range | Maximum minus minimum. | A large span may suggest an outlier or mixed units. |
| Minimum, Maximum | Smallest and largest accepted numbers. | Compare with expected bounds. |
| Mean, Median | Arithmetic mean and middle value of accepted numbers. | A blank median means its measure reached a scan limit. When the second pass computed it, it is shown with `exact` (counted per integer) or `est.` (estimated from bins, with its bounds in the tooltip). |
| Distinct, Examples | Normalized value count and retained value examples. | These describe value representation, not the calculation of numeric statistics. |

Configured number conventions can accept comma decimals such as `12,5`. Check
type errors in **Columns** before treating these statistics as representative
of every present value.

## Date analysis

**Purpose:** separate recognized date and time values, ambiguous readings,
invalid date-shaped values and other present values.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Status | Summary of the field's date results, such as valid, ambiguous, invalid, mixed or multiple formats. | Use the counts before assuming the whole field is a date. |
| Breakdown | Counts by valid format and by ambiguous, invalid or non-date category. | See which form creates uncertainty. |
| Valid | Unambiguous recognized date, date-time or time values. | Percentages use eligible present values, not all rows. |
| Ambiguous | Values such as `02/03/2026` that fit both DMY and MDY. | Other values in the column do not resolve their order automatically. |
| Invalid | Date-shaped values with impossible content, such as `2026-02-30`. | Check the source value and the configured rules. |
| Other | Present values that did not match as dates or were not tested. | See whether a missing marker or another format was expected. |
| Distinct, Formats | Normalized distinct values and recognized date formats. | Open the formats tooltip for counts; ambiguity evidence is in the column details. |

Only an explicit `scan.detectors.date.ambiguous_order` setting resolves an
ambiguous order. The report shows unambiguous DMY/MDY evidence but does not
apply it to ambiguous values.

Below the table, **Distribution over time** counts the valid dates of a column per
day, month or year, exactly, when the second pass computed them. A date is placed
by the date it is written with; ambiguous dates are counted apart and never
placed, unless the unambiguous dates of the column prove one day-month order: the
second pass then reads them with it and the row says so. Open a column to see its periods; the table is the alternative to a chart.

## String analysis

**Purpose:** inspect the lengths of inferred `text` columns. Missing values
do not contribute to lengths.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Class | `very_short`, `short`, `medium`, `long` or `very_long`, based on the maximum observed length and the `scan.classification` bounds. | This is a length class, not the Text type of the column. The Text type of the Scan [classification](../scan/format.md#classification) uses the same bounds on the median length, so the two can differ. |
| Fixed | One length when minimum and maximum agree. | A fixed width alone does not prove a field is an identifier. |
| Min, Max, Mean, Median | Length statistics for present text. | These cells are blank for a fixed-length field because **Fixed** already conveys its length. |
| Lengths | Frequency of each length, when the maximum fits the configured distribution limit. | The tooltip includes bounded examples per length. |
| Distinct, Examples | Value count and retained examples. | These concern values, not the number of distinct lengths. |

### Character map

The text panel of a column page ends with the character map. It says whether the figures count every
value of the column (the second pass, or a scan that kept every distinct value) or the sample of
distinct values the scan stored.

| Block | What it shows |
| --- | --- |
| Most frequent characters | The 20 most frequent characters, letters and digits included, with their code point and their share of all the characters. A space, a tab or an invisible character is drawn as a mark or its code point. |
| Scripts of the letters | The share of the characters of each script (Latin, Cyrillic, CJK...). |
| Kinds of characters | The share of each Unicode category: lowercase and uppercase letters, digits, punctuation, spaces... |
| Case of the values | The share of the values that end with a capital, end with a lowercase letter or are in title case. These shares are of the values, not of the characters. |
| Emoji | The values with an emoji and the most frequent emoji sequences. |

A masked or hidden column has no character map. A map that passed its bounds says so and lists nothing.

## Detectors and formats

**Purpose:** inspect the evidence behind the type of a column. Each row
pairs one column with a detector that found evidence or failed. See
[Recognized patterns](../reference/types-and-patterns/patterns.md#built-in-detectors) for
the complete detector catalog.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Column, Detector | Field and detector ID. `primary` marks the interpretation the classification starts from. | Several detectors may appear for one field. |
| Matched | Recognized values as a count and percentage of eligible values. | A match checks the detector's rules, not real-world existence. |
| Ambiguous, Invalid | Values with multiple readings or a recognized shape with invalid content. | These are separate from **Matched** and from column type errors. |
| Formats | Recognized forms with counts and percentages in the tooltip. | Formats describe syntax; their set varies by detector and configuration. |

A `failed` detector has no usable coverage for that field. Adaptive detection
can skip values after a warm-up; inspect tested and not-tested counts in the
[JSON profile](json-profile.md#detectors) or a standalone column page before
treating a low match rate as full-field coverage.

## Patterns

**Purpose:** show the structural patterns of text columns, inferred from the
distinct values the scan sampled, grouped by family. A family gathers the values
of one structure (capitals, a hyphen, digits); it is presented as its patterns,
each of a fixed length. A pattern writes `9` for a digit, `A` for a capital, `a`
for a lowercase letter, `@` for a letter of any case or script, `X` for a capital
or a digit, `x` for a lowercase letter or a digit and `#` for an ASCII letter or a
digit. Text between quotes is a constant that every value of the pattern shares:
`'AK-'9999`.

The table of the dataset has one row per pattern. Each column page has the whole
hierarchy, readable without JavaScript:

- a **family** block with its structure (`UP-D`), its distinct values and
  occurrences, and, when the second pass ran, how many values of the whole file it
  reads;
- its **patterns** (`'INV-'999`, `'INV-'9999`), with the commonest format, their
  token lengths, examples and counts;
- indented **nodes** under a pattern: a node fixes the start or the end of a
  token, or a short token (`'AK-'9999` under `AA-9999`), and its line shows the
  bits the choice saves. A node with children can be folded;
- **tables** of a family, for a facet that no node reads: its cells and an
  *others* row add up to the family.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Column, Family, Pattern | Field, family (structure and id) and pattern, with its role: `principal` for the most common. | A secondary pattern can be a second format in use, or a rare mistake. |
| Distinct values, Share | Distinct values the pattern takes, and their share of the distinct values read. | A share counts distinct values, never occurrences in the file. |
| Basis | exact when the scan held every distinct value of the field, sample when it held a sample of them. | The share is of distinct values, not of the file. |
| Validated on every value | When the second pass ran: how many values of the whole file the pattern reads, and their share of the values of the column. | Exact. A value is counted for one pattern, the one of its family that has its lengths. |
| Length, Examples | Length of the pattern in characters, and examples among the values the report keeps. | An example the report does not keep is not shown. |

A value counts for one pattern, the one of its family that has its lengths. The
row *unmatched* counts the values no pattern takes; with the second pass, its
validated figure is the number of values of the whole file that no pattern reads.
A column page also lists the *new variants* the second pass found in a known
family: a value whose lengths, or whose segment, the sample never showed. These
are observations about structure, not errors. A column with no pattern, such as a
number or a masked column, says why on its own page.

## Relationships

**Purpose:** show how one column goes with another, from the second pass. The section
appears when the second pass computed a table of a category against a feature, or a
correlation of two numeric columns, and sits before the Insights section.

| Report part | Meaning | What to check |
| --- | --- | --- |
| Heading | The category and the column it is read against, with the number of features computed. | The same two columns are one block, whatever the number of features: the pattern, the length and the prefix of an identifier often say the same thing. The best one comes first and the others are folded. When two columns are listed in both directions (region by city, then city by region), the weaker direction follows the stronger one, folded under "The same pair the other way round". |
| Metrics | Classified rows (and the rows left out), purity, association and exceptions. | Purity is the share of each category's rows in its dominant class; compare it with what the most frequent class would give. |
| Table of counts | For each category, the exact count of its rows in each class and its share, with its total, coverage and purity. | The percentages come first: read them before the score. The dominant class of each category is underlined. A class that is empty for every category is `other`, hidden when it is empty. |
| Exceptions | The rows outside the dominant class of their category, with exact counts and the first rows in file order. | They are the rows to look at to decide whether a pattern is a rule of the data. |
| Candidate rules | Relations learned from the data, such as "when region is QC, client_id reads XX9999". | They are candidates, learned and not validated. |
| Correlations | The coefficient of pairs of numeric columns, over the rows where both have a number. | A correlation is a linear association, not a cause. |

The association is Cramér's V, corrected for the number of rows and classes, with a
word: negligible, weak, moderate or strong. When the counts are too low to trust it,
it says *Unstable: low counts* instead of a word. A category or class of fewer than
5 rows does not cause it by itself. A table with only one category or one class has no score and says why. Every
count is exact. A note under the tables says what the planner explored on the rows the
scan sampled: a relation that sample does not show can still exist in the file.

## Insights

**Purpose:** show what the later analyses of the second pass found, one card per
analysis and column, with the accuracy of each figure. The section appears when the
second pass computed at least one of them, and sits before the Second pass section.
The page of each column (`--details`) shows the cards that concern it, and what the
report reads from the Scan for that column.

| Family | What a card tells | What to check |
| --- | --- | --- |
| Values with a unit | The numbers read from amounts, percentages and quantities: how many, how many were ambiguous, invalid or not read, the numbers of each unit (minimum, median, mean, maximum) and their distribution. | Units are never converted. When a column mixes units, the overall figures are not shown and each unit is read alone. A percentage above 100 is counted, not corrected. |
| Shape of the numbers | Skewness, excess kurtosis, quartiles, the outliers of Tukey (mild beyond 1.5 and far beyond 3 interquartile ranges), the decimals the numbers are written with, and two views of their spread: bins of equal ratio and bins of about equal counts. | The outliers are a rule of thumb, not errors. With many distinct numbers the quartiles are estimates and the outliers are given as a range. |
| Parts of the dates | The day of the week, the hour, the month or year, the dates after a cut-off when one is configured, the invalid dates by reason and, for ambiguous dates, what each reading would change. | Dates are counted as written; an offset is never converted. The simulation changes nothing. |
| Values left out | The values no pattern reads and the values a detector finds invalid or does not match, with their exact counts and first record, and every pattern over every occurrence. | A list is bounded when it says so; the counts of the values it holds stay exact. |
| Repeated values | The values found more than once, their occurrences and first record, and the combinations of two columns when asked for. | Without the source, the first record is absent. |
| Numbers by category | For each value of a category, its rows, how many have a number, and the minimum, median, mean and maximum, with the share of the variance the categories explain. | It shows an association between two columns, not a cause. |
| Drift along the file | The records, values and missing values of each tenth of the file, how strongly the position tells them apart (Cramér's V), and for a column of few values their share in each tenth and the tenth where each first appears. | A change along the file shows that the column was filled or exported differently, not why. The tenths hold the same number of records, so a longer bar is a part of the file that misses more. |
| Missing together | For the dataset, the pairs of columns that lack a value in the same records; on a column page, the other columns that lack a value where it does, with their counts and the share where both do. | Every count is exact. It shows that values go missing together, not why. A pair of columns that miss often can overlap by chance: compare *Both* with what the two counts would give if independent. |
| Structure of the JSON | The lengths of the arrays of a field (every length, the quantiles) and the sets of keys the objects have, with the keys each set lacks; the sets of keys of the records themselves sit in the dataset panel only. | Counts are exact. A list of sets that says it is not complete counts at least that many sets. It shows that objects differ, not why. |
| Long texts | The words, lines and digits of the texts by powers of two and by tenth of the characters, and the distinct texts told apart by a 128-bit fingerprint with the ones found most often, by digest. | The fingerprint count carries its own label: two different texts are taken for one only if their digests collide. The texts themselves are never kept. |
| Sensitive columns without a value | The masks of a masked column and their exact counts, and for addresses and phone numbers the count by class. | No value is listed, and no count below the floor of `deep.sensitive.min_count`: masks and classes with fewer values are summed up. The card is not printed for a column that hides its values, and the analysis is off until `deep.sensitive.enabled` is set. |
| Read from the Scan | On a column page only: the quartiles of the lengths, the values outside the listed frequencies, the dominant unit, the dates by decade and the empty periods. | Computed from the document, without reading the source. |

Every figure carries its own label (see [How counts are
qualified](#how-counts-are-qualified)), because one card can hold exact counts beside
an estimated median: when the distinct numbers pass `deep.measures.max_values`, counts,
sums and extremes stay exact and the quantiles are estimates between certain bounds.
A card from a report built from a scan document says which figures come from the values
the Scan kept.

When the unambiguous values of a column prove how its ambiguous ones are written, the
card says it: *150 read as DMY, proved by 150 unambiguous dates* for dates, or *75 with
the decimal comma convention, proved by 150 unambiguous values* for numbers. The
ambiguous values are then counted with the others. Values of a column with an exposure
of `mask` or `hide` are never listed.

## Second pass

**Purpose:** say what the second pass added to the report and what it left out. The
report runs it by itself for the analyses that are useful and cheap; `tabalyst
report --deep` forces it. The section is absent from a report made before the
second pass existed.

| Report part | Meaning | What to check |
| --- | --- | --- |
| Introduction | Who decided (automatic, forced or off) and how the second pass ended. | A report built from a scan document reads no source and says so. |
| Computed, Not computed | Analyses with a result, and those skipped or failed. | A skipped analysis says why in its row. |
| Already answered, Not selected | Analyses the scan already answers, and those the planner left out. | The reasons are listed under the table: too little benefit, a mixed type, a value too long for an exact set. |
| Table | Each analysis with its status, what it found and its accuracy. | Exact counts are marked exact; a stopped distinct count is a lower bound. |
| Footnote | Whether the source was read again and checked against the digest of the scan. | The source is checked, so no result mixes two versions of the file. |

The results of the later analyses are laid out in [Insights](#insights). The second
pass also completes figures elsewhere: the exact distinct count of a
column the scan stopped counting (marked *2nd pass*), the median of a numeric
column, the validated occurrences of each pattern and the distribution of dates
over time.

## Limits and diagnostics

**Purpose:** make incomplete measures and technical scan events visible.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Field, Measure | Where and which measure stopped. A dataset-level measure has no field. | Check whether the affected measure is needed for your conclusion. |
| Reason, Limit | Why it stopped and the configured bound. | Adjust the relevant [scan limit](../reference/configuration.md#limits) if needed. |
| At least | A proven lower bound, when one is available. | Do not treat it as an estimate of the final count. |

The section also lists **Diagnostics** (code, level, count and bounded record
locations), **Untracked observations** beyond the field limit, and
**Truncated by depth** observations beyond the reader depth limit.

## Data sample

**Purpose:** inspect rows of the dataset in three labelled parts: the first
records (**Start**), records drawn at random from the interior (**Sampled**) and
the last records (**End**). The report shows 10 of each by default
(`report.row_sample`). The sampled rows are not uniform over the whole file: the
first and last records are kept separately. The sample does not limit the full
analysis, and sorting and filtering the table only change the display.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Row, Part | Record number in the dataset, starting at 1, and the part the row comes from. | A CSV or Excel header is excluded. |
| Each field | Raw source value under its column name and inferred type. | Sensitive values can be masked or hidden; `absent` in JSON differs from explicit `null`; `… cut` marks a cell the scan cut at `scan.records.sample.cell_chars` characters. |

## Analysis settings

**Purpose:** reproduce and interpret the report. This final section gives the
effective scope, missing markers, normalization, type and date rules, detector
thresholds, exposure policy, value representation, row sample and source
SHA-256, and for the identifier columns the rule version, the sources of the
copies of rows actually used and the Dedup reports read or refused. Consult it whenever a count or match differs from your expectation;
the [configuration reference](../reference/configuration.md) explains how to
change the settings.
