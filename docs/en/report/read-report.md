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

Three cards sum what the checks found and how far they went, as KPIs. They add up
the findings of the [column summary](#column-summary), column by column, and never
guess: a sum only joins findings of one kind counted in one unit. Every figure that
stands for columns opens a popover (click, Enter or Space; Escape closes it and gives
the focus back) with the columns behind it.

- **Column quality** shows how many columns have Errors, Issues only, or no finding,
  as figures, percentages of the columns and one bar. A column with Errors counts under
  Errors even when it also has Issues, so the three figures add up to the columns. Each
  figure opens the columns of its group with their findings. A line counts the
  observations of the scan by status (*confirmed issue*: a defect by the structure of the
  source; *candidate anomaly*: worth a look and never proof of an error; *remark*: may be
  perfectly valid, such as a constant column), with the meaning in its `?` popover.
- **Signals** gives one tile per kind of finding present, with a large figure, a title
  and a line that says what it counts: type mismatches, invalid values, spelling
  variants, ambiguous dates, repeated whitespace, minority lengths... Errors come first
  in a red tile, then Issues, each ordered by the columns touched. `≥` marks a sum with
  a lower bound. The **N columns** button opens the columns with their figure and, by
  case, their details: the largest group of spelling variants of each column, or the
  note that Tabalyst does not guess the order of an ambiguous date. Six tiles are shown;
  the others are counted.
- **Column types** counts columns twice, not cells: by family and type of the
  classification, then by technical type.

The overview, the column summary and the findings answer different questions: how
much and how far, which column, and what exactly. See
[Findings](json-profile.md#findings).

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
| Detail | The first record numbers, the patterns and the limits behind the finding. For spelling variants, the largest groups with their spellings and counts, the most frequent first. | Use the record numbers to find the rows in the source. In a group of variants, the most frequent spelling is the likely target of a correction; the others are the candidates to review. A masked column shows merged masks, a hidden one nothing. |

The table shows 25 findings at a time and up to 500; the JSON profile lists
them all. Without observations (`scan.observations.enabled` is `false`) the
section says that they are not computed.

## Column summary

**Purpose:** read each field in one row: its classification, a factual sentence
about it, its completeness and its findings. The classic **Columns** table, with
the technical type, sits right after it. Each row is one field, identified by its dataset and
its field `id`, never by its name alone. **Quality issues** filters to fields
with an Error or an Issue in the table; **With observations** keeps the fields
the scan has an observation about, remarks included.

| Report column | Meaning | What to check |
| --- | --- | --- |
| Column | Name and source position. JSON paths identify nested fields; names in a table may be blank or repeated. | Use position, the path under the name or the JSON profile's stable `id` when a name is ambiguous. |
| Type family | The family of the [classification](../scan/format.md#classification): `Identifier`, `Categorical`, `Numeric`, `Temporal`, `Contact`, `Geographic`, `Web / Network`, `Text` or `Other`. | Filter and sort here to see every field of a family; the filter is independent of **Type**. |
| Type | The type inside the family, such as `Unique ID`, `Enum`, `Email` or `Short` (a `Text` length). | An identifier type is a candidate that rests on a name and the values; the JSON profile gives the `state` and the `evidence` of every type. See [Types](../reference/types-and-patterns/types.md#classification). |
| Overview | One factual sentence about the field: distinct values, range, recognized formats, median length. | It states no business meaning and never repeats an Error or an Issue. `at least` marks a figure that is a lower bound. |
| Missing | Missing positions as a count and percentage of this field's positions. Absent JSON members count in the denominator. | A missing value is never an Error or an Issue by itself. Check the missing markers in **Analysis settings**. |
| Errors | Values a deterministic rule proves invalid, such as an impossible date or a malformed email, in a field whose type is established. | Each label gives its count in its own unit. `None detected` means the checks ran everywhere; a dash (`-`) means `Not applicable`: no rule exists for this type. |
| Issues | Ambiguities and deviations to inspect, such as ambiguous dates, spelling variants or a minority length. | A rare value is not an invalid one. Under a list, a line such as `1 check partially assessed` names a check that did not cover every value. |
| Details | A few values of the field on two lines at most. The hover (or focus, or a tap) holds the whole story: the values with their counts and shares, every Error and Issue label of the column, the groups of spelling variants with their spellings (the most frequent first) and the complementary measures. | A list can be complete or bounded. Sensitive values can be masked or hidden. |

The states of Errors and Issues are written: `None detected`, `Not assessed`,
`Partially assessed`, `Not applicable` and `Assessment failed`. The only dash is
the `Not applicable` of an Errors cell, which keeps its word in the filter and for
a screen reader. Two labels are shown in a cell, then `+N more`. The technical
type of the field (`inferred_type`) is not a column of this table; it stays in
the **Columns** table, in the JSON profile and on the column page.

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
SHA-256. Consult it whenever a count or match differs from your expectation;
the [configuration reference](../reference/configuration.md) explains how to
change the settings.
