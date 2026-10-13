---
title: JSON profile changelog
description: Current format version and revisions of the JSON profile written by tabalyst report.
---

The JSON profile written by `tabalyst report` identifies its experimental
contract with two fields:

```json
{
  "format": "tabalyst.report",
  "format_version": "0.2.0",
  "format_revision": 2
}
```

`format` identifies the document kind: a report is a
[scan document](../scan/format.md) with a `report` block. `format_version` names the compatibility family. `format_revision` increases
for a meaningful structural or semantic change within that family. Styling,
documentation, performance improvements and corrections that preserve the
JSON contract do not change it. Beta revisions may be incompatible; automatic
migration is not provided.

## Version 0.2.0, revision 1 — 2026-10-06

This is the starting point for the current [JSON profile](json-profile.md).
It describes the existing Report profile, including CSV, JSON, JSONL and Excel
sources, effective settings, dataset summaries, column analysis, normalization,
detectors, issues, record previews, limits and JSON structure.

## Version 0.2.0, revision 2 (2026-10-10)

The profile becomes a superset of the Scan document: it has `format:
"tabalyst.report"` and holds the scan base at the same paths (`engine`,
`status`, `run`, `source`, `config`, `config_sha256`, `scope`, `datasets`,
`diagnostics`), plus a `report` block.

- The report's own data moves under `report`: `generated_at`,
  `processing_seconds`, the presentation settings (`report.config`, with only
  `string_analysis` and `value_examples`, the `report` object of the
  configuration files; the root `config` is the scan configuration), `base_scan` (identity of the base) and the projections
  (`report.datasets`, with the summary, columns and structure of each dataset). The root `datasets` are the scan datasets.
- `source` is the scan's: `filename` becomes `name`, `delimiter` is
  `source.csv.delimiter` (`null` `csv` for other sources).
- The column copies of scan facts are removed: `scan_details`, `numeric`,
  `string_profile` and `date_profile`. They are read from the fields of the
  base.
- The samples of the base are reduced and declare `kept` and `of`. How many
  values the report keeps per column is a presentation setting,
  `report.config.value_examples.kept_per_column` (1 to 1,000, 100 by default).
- A report carries the optional `derived` member of its scan, the
  [inferred patterns](../scan/format.md#inferred-patterns), as it is: the
  reduced samples cannot compute them again.
- A report carries the optional `observations` member of its scan, the
  [observations and limits](../scan/format.md#observations-and-limits), as it
  is.
- The report reads its findings from the base instead of storing its own:
  `report.datasets[].issues`, `preview` and `limits`, `columns[].with_issues`
  and `summary.with_issues_column_count` are removed. A column has quality
  issues when an observation about its field is a confirmed issue or a
  candidate anomaly; a remark such as missing values is not an issue (see
  [Findings](json-profile.md#findings)).
- The rows the report shows are the `records.sample` of the base, reduced:
  the first, the interior rows of smallest priority and the last rows, as the
  new presentation setting `report.config.row_sample` (`start`, `middle`, `end`,
  10 each by default) asks. `kept` and `of` say what was kept.
- A report carries an optional `analyses` member, [what its second
  pass did](json-profile.md#analyses): who decided it, the outcome, and the second
  pass document with its plan and its results. The HTML report adds the Second pass
  section, the validated occurrences of each pattern, the dates per period, and the
  exact distinct count and median that a scan limit had stopped. The second pass
  document inside `analyses` also holds the correlation of pairs of numeric columns
  (`partner` on an analysis, the result `pearson`, `relations` and `exploration` in
  the plan) and the tables of a category against a feature (the result `crosstab`,
  `relations.tables`, the domain `mixed`). The HTML report shows both in a
  Relationships section before the Second pass section.
- The HTML report adds the Observations and Patterns sections, qualifies every
  count as exact, estimated, sample, at least or not computed, and writes
  integers with all their digits (see
  [Large integers](json-profile.md#large-integers)).

## Version 0.2.0, revision 3

The report follows the scan base at revision 3 (see the
[Scan format changelog](../scan/format-changelog.md)): `numeric.coverage`, the
refusal of `numeric` for codes, the `minority_length` observation and the
ambiguous numbers read in the convention their column proves, which the
numeric statistics of the report now include. The report adds no member of its
own. The second pass document inside `analyses`
is at [revision 2](../scan/deep-format.md#changelog): it may hold the numbers of
amounts, percentages and quantities with a unit (the result `measures`), which
the Second pass section summarizes in one line, the values that patterns and
detectors leave out (`residual_values`) and the repeated values of identifiers
and keys (`duplicates`, `duplicates_limited`), the line and the rank correlation of a
pair (`slope`, `intercept`, `rank`), and the tables of a category against the values
of another column with the rules you gave (`provided_rules`), and the numbers of a column
described by category (`category_stats`: count, extremes, mean, spread and histogram of each
category, and the share of the variance the categories explain), the shape of the numbers
(`numeric_shape`: asymmetry, kurtosis, outliers of Tukey, decimals) and the parts of the dates
(`datetime_parts`: year-month, weekday, hour, ambiguous dates under each reading), the drift of a column along the
file (`position_drift`: the records, values and missing values of each tenth of the file) and the columns that
miss a value together (`missing_matrix`), the lengths of the arrays and the sets of keys of a JSON file
(`array_profile`, `structure_variants`), the words, lines and digits of long texts and their 128-bit
fingerprints (`text_profile`, `fingerprint_distinct`) and the masks and classes of a masked column
(`sensitive_forms`), which holds no value of it, and the distinct count of a masked or hidden column.

## Version 0.2.0, revision 4 (in preparation)

The report follows the scan base at revision 4 (see the
[Scan format changelog](../scan/format-changelog.md)): the eligibility of each
field for the inferred patterns and the character profile of its strings
(`string_characteristics`). A column page says why a column has no pattern with
the reason of its eligibility, and lists the characters of the profile. The
inferred patterns are the families and patterns of grammar 2 (see the Scan
changelog); the page lists the patterns of a column. The patterns carry nodes of content (the
first or last characters of a token, a whole token) with their gain, and tables of
content, as the Scan changelog says. The `pattern_counts` result of the second pass that the report carries
under `analyses` follows the hierarchy too (revision 3 of the [second pass format](../scan/deep-format.md)):
families, patterns and nodes with their occurrences, distinct values and tables. The report adds no member of its own. The HTML page of a column presents the hierarchy (families, patterns, indented nodes and tables, readable without JavaScript) and the table of the dataset names the family of each pattern; nothing of the JSON changes.
