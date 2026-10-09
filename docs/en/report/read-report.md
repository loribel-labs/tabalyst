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
| not computed | The scan did not compute it, for example when `scan.observations.enabled` is `false`. |

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

The **Quality observations** card groups the findings of the scan by rule, each
with its status: a *confirmed issue* is a defect of the source by its structure,
a *candidate anomaly* is worth a look and never proof of an error, and a
*remark* may be perfectly valid, such as a constant column. **Column types**
counts columns by inferred type and semantic type, not individual cells. The
date card sums ambiguous values across date columns, so one record can
contribute more than once. See [Findings](json-profile.md#findings).

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
| Detail | The first record numbers, the patterns and the limits behind the finding. | Use the record numbers to find the rows in the source. |

The table shows 25 findings at a time and up to 500; the JSON profile lists
them all. Without observations (`scan.observations.enabled` is `false`) the
section says that they are not computed.

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
| Semantic type | One primary detected meaning, such as `email` or `postal_code`. | A dash means there is no unique qualifying interpretation. Other detectors may still have matched. See [semantic types](../reference/types-and-patterns/types.md#semantic-types). |
| Error | Count and percentage of present values outside the inferred type. | This is type disagreement, not malformed records or detector failures. It is unavailable for `mixed`. |
| Issues | Confirmed issues and candidate anomalies about this field, with the number of remarks below. | Open the column page or **Observations** for the detail. |
| Examples | A few retained values; the tooltip gives more values and counts. | A distribution can be complete or a bounded sample. Sensitive values can be masked or hidden. |

Missing values do not lower type confidence. For example, `not available` can
disagree with a numeric type if it was not configured as a missing marker. An
email field can have inferred type `text` and semantic type `email`: these
answer different questions. Add `--details` to link each column to its own
page with scan evidence and value counts:

```console
tabalyst report customers.csv --details
```

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
| Mean, Median | Arithmetic mean and middle value of accepted numbers. | A blank median means its measure reached a scan limit. |
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

## String analysis

**Purpose:** inspect the lengths of inferred `text` columns. Missing values
do not contribute to lengths.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Class | `very_short`, `short`, `medium`, `long` or `very_long`, based on the maximum observed length and configured thresholds. | This is a length class, not a semantic type. |
| Fixed | One length when minimum and maximum agree. | A fixed width alone does not prove a field is an identifier. |
| Min, Max, Mean, Median | Length statistics for present text. | These cells are blank for a fixed-length field because **Fixed** already conveys its length. |
| Lengths | Frequency of each length, when the maximum fits the configured distribution limit. | The tooltip includes bounded examples per length. |
| Distinct, Examples | Value count and retained examples. | These concern values, not the number of distinct lengths. |

## Detectors and formats

**Purpose:** inspect the evidence behind a possible semantic type. Each row
pairs one column with a detector that found evidence or failed. See
[Recognized patterns](../reference/types-and-patterns/patterns.md#built-in-detectors) for
the complete detector catalog.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Column, Detector | Field and detector ID. `primary` marks the interpretation shown as semantic type in **Columns**. | Several detectors may appear for one field. |
| Matched | Recognized values as a count and percentage of eligible values. | A match checks the detector's rules, not real-world existence. |
| Ambiguous, Invalid | Values with multiple readings or a recognized shape with invalid content. | These are separate from **Matched** and from column type errors. |
| Formats | Recognized forms with counts and percentages in the tooltip. | Formats describe syntax; their set varies by detector and configuration. |

A `failed` detector has no usable coverage for that field. Adaptive detection
can skip values after a warm-up; inspect tested and not-tested counts in the
[JSON profile](json-profile.md#detectors) or a standalone column page before
treating a low match rate as full-field coverage.

## Patterns

**Purpose:** show the structural patterns of text columns, inferred from the
distinct values the scan sampled. A pattern writes `9` for a digit, `X` for a
capital, `x` for a lowercase letter, `@` for any letter and `#` for a letter or a
digit; other characters are written as they are, and a letter or digit that is
fixed in every value is quoted, such as `'ONT'9{6,7}`.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Column, Pattern | Field and pattern, with its role: `principal` for the most common. | A secondary pattern can be a second format in use, or a rare mistake. |
| Distinct values, Share | Distinct values the pattern takes, and their share of the distinct values read. | A share counts distinct values, never occurrences in the file. |
| Basis | exact when the scan held every distinct value of the field, sample when it held a sample of them. | A pattern is not validated against the whole file. |
| Lengths, Examples | Observed lengths, and examples among the values the report keeps. | An example the report does not keep is not shown. |

A value counts for one pattern, the most specific that reads it. The row
*unmatched* counts the values no pattern takes. A column with no pattern, such as
a number or a masked column, says why on its own page.

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
SHA-256. Consult it whenever a count or match differs from your expectation;
the [configuration reference](../reference/configuration.md) explains how to
change the settings.
