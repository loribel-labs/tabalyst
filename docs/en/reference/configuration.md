---
title: Configuration
description: Reference for the JSON configuration file read by tabalyst report, tabalyst sample, tabalyst scan and the Python API.
---

Tabalyst reads strict JSON configuration files. JSON does not allow comments;
this page is the descriptive reference for supported settings. Commands load
the files passed with `--config`, and the Python API those passed with
`config_path`; no file is loaded automatically. `tabalyst.json` is only a
conventional name.

One file can configure every command, with one object per tool. The `scan`
object holds the analysis settings, read by `tabalyst scan` and
`tabalyst report`, described in [Scan settings](#scan-settings). The `report`
object holds the presentation settings of the report, described in
[Report settings](#report-settings). The top-level `output` object sets how
the documents are written, described in [Output settings](#output-settings).
The top-level `deep` object sets the histograms of the second pass, described
in [Deep settings](#deep-settings).
The top-level `csv` object holds the CSV settings of `tabalyst sample`:

```json
{
  "report": {"string_analysis": {"examples_per_length": 5}},
  "csv": {"delimiter": ";"},
  "scan": {
    "csv": {"delimiter": ";"},
    "values": {"null_markers": ["N/A"]},
    "records": {"duplicates": true}
  }
}
```

Every command validates the whole file, including the sections it does not
use, so a misspelled or unknown setting is always an error. Explicit
command-line values, such as `--delimiter` and `--encoding`, are the final
override.

## Report settings

The report is built on Tabalyst Scan: it reuses a current stored scan when
possible, or reads the CSV with the effective `scan` settings, then presents
the result with the settings of the `report` object below. They only shape the
presentation: changing them never scans the source again.

```json
{
  "report": {
    "string_analysis": {
      "length_distribution_max_length": 50,
      "examples_per_length": 10
    },
    "value_examples": {
      "kept_per_column": 100,
      "full_distribution_max_distinct": 50,
      "short_text_max_length": 20,
      "short_text_percentile": 0.95,
      "short_text_result_size": 20,
      "long_text_result_size": 20,
      "long_text_truncate_at": 30,
      "truncation_suffix": "...",
      "inline_display_size": 3
    },
    "row_sample": {"start": 10, "middle": 10, "end": 10}
  }
}
```

### Row sample

The report shows rows of the [row sample](../scan/format.md#row-sample) of the
scan: the first `report.row_sample.start` records, the last `end` records and
`middle` records drawn from the interior, 10 of each by default, at most 1,000
of each and never more than the scan kept (see [Records](#records)). The sampled
rows are the ones with the smallest priorities, a subset of the scan's, and are
not uniform over the whole file. The setting never limits the analysis of the
complete file, and changing it never scans the source again. Values of sensitive
columns are masked or hidden as in the rest of the report (see
[How the report uses the scan settings](#how-the-report-uses-the-scan-settings)).

### String analysis

Present values in `text` columns are classified from their maximum length as
`very_short`, `short`, `medium`, `long` or `very_long`, with the bounds of
[`scan.classification`](#text-length-bounds) (5, 20, 50 and 255 characters by
default). The Text type of a column is decided on the same bounds, but on the
median length: a column can be Short as a type and `medium` in this section when
a few values are long. A fixed length is
recorded separately when minimum and maximum match. Missing values do not
contribute to lengths. Mean and median length are calculated for every text
column; the report leaves them blank when the fixed length already conveys the
same information.

`length_distribution_max_length` cannot exceed `scan.classification.medium_max_length`;
the two settings are in different objects, so the report stops with an error
when they disagree. When the column maximum is at most `length_distribution_max_length`, JSON also
contains the exact occurrence count of every observed length. Each length lists
up to `examples_per_length` example values, taken from the most frequent values
of the column, then from its sampled values. `distinct_length_count` remains
available for every text column, including columns whose distribution is
omitted. The report orders length groups by occurrence and shows three examples
per length in its String analysis tooltip.

### Examples and value profiles

- `kept_per_column`: how many values of the scan sample the report keeps and
  draws its examples from, from 1 to 1,000 (default `100`). The report keeps
  the whole scan sample when it has no more values, otherwise this many of its
  values: the ones of smallest hash priority, which the scan sample would also
  keep at that size. The report declares how many it
  kept and how many the scan listed in `values.samples` (`kept` and `of`). A
  larger `scan.limits.max_samples` therefore does not change the examples of the
  report. Choosing diverse examples compares the values with
  each other, so the time grows faster than the number: on the 34 columns of
  the insurance example, a report from a scan takes about 1 second at 100
  values, 3 seconds at 300 and 30 seconds at 1,000, the maximum.
- `full_distribution_max_distinct`: through this limit, every present distinct
  value and its occurrence count are retained in JSON. At `50`, the
  distribution is still complete; at `51`, Tabalyst selects values among a
  reproducible sample of at most `kept_per_column` distinct values.
- `short_text_max_length` and `short_text_percentile`: a column is considered
  short text when this percentile of its sampled lengths does not exceed the
  configured length.
- `short_text_result_size`: **number of values retained for the tooltip when a
  short-text column has more than 50 distinct values.** Its default is `20`.
- `long_text_result_size`: equivalent limit for long text. Its default is also
  `20`.
- `long_text_truncate_at` and `truncation_suffix`: display limit for retained
  long-text values in both JSON and the report.
- `inline_display_size`: number of values shown directly in the `Examples` cell.
  They are always the most frequent retained values.

The `Examples` cell shows `+N` for a complete distribution. For a sampled profile,
it shows `++`; the tooltip then shows, for example, `20 / 2,992`, meaning retained
values / actual distinct values. Tooltip values are sorted by descending occurrence
count. For a sensitive column, the cell shows `masked` or `hidden` instead, and
the tooltip lists masked values.

### How the report uses the scan settings

| Report behavior | Scan settings |
| --- | --- |
| Reading the CSV | `scan.csv`, `--delimiter`, `--encoding` |
| Missing cells | `scan.values`: `null_markers`, `null_markers_case_sensitive` and `missing` |
| Normalization counts, distinct values and variant groups | `scan.normalization`: `nfc`, `trim`, `collapse_whitespace`, `casefold`, `strip_accents` |
| Inferred types | `scan.types.minimum_confidence`, with the `number` and `date` detectors |
| Date analysis | `scan.detectors.date` |
| Semantic types | `scan.detection.minimum_share` and every detector |
| Masked values | `scan.exposure.sensitive_values` |
| Row sample (first, middle and last rows) | `scan.records.sample` for the rows the scan keeps, `report.row_sample` for the rows the report shows |
| Duplicate rows | `scan.records.duplicates` and `scan.limits.max_tracked_records` |
| Limits and diagnostics | `scan.limits` and `scan.errors` |

- **Dates.** A column whose present values are dates is `date`, even with
  several formats or ambiguous values. Ambiguous values such as `02/03/2025`
  are never resolved from other values of the column: the report counts them
  as ambiguous, shows how many unambiguous values use each order and, when only
  one order appears, suggests setting `scan.detectors.date.ambiguous_order`.
  The `ambiguous_dates` issue counts them.
- **Semantic types.** `date` for date columns, otherwise the scan's primary
  interpretation: the only detector matching at least
  `scan.detection.minimum_share` of the present values, such as `enumeration`,
  `email`, `phone` or `postal_code`. `number` and `boolean` are not repeated as
  semantic types.
- **Sensitive values.** Sensitive columns are not handled in this beta: by
  default every value is shown, including in examples, value profiles and the
  data sample. Set `scan.exposure.sensitive_values` to `mask` to replace the
  values of columns where a sensitive detector matches, such as email addresses
  and phone numbers (`jane@example.com` becomes `aaaa@aaaaaaa.aaa`), or to
  `hide` to remove them.
- **Limits.** When a scan limit stops a measure, such as the distinct values
  of a column with more than `scan.limits.max_distinct_per_field` of them, the
  report shows `limited` instead of a number and lists the column in the
  `limited_measures` issue.
- **Duplicate rows.** With more distinct rows than
  `scan.limits.max_tracked_records`, the duplicate count is a lower bound,
  shown as `≥ 12`. With `scan.records.duplicates` set to `false`, duplicates
  are not checked and the report shows `–`.

The report reads the `scan.csv` settings, not the top-level `csv` settings. When
a file sets both with different values, the report stops with an error, since
the file would otherwise be read with settings it does not expect; a value
given with `--delimiter` or `--encoding` always wins. The report also needs
every column: a CSV wider than `scan.limits.max_fields` is an error.

A report built from a scan document with `tabalyst report --scan` uses the
settings recorded in the document. Its configuration files still give the
presentation settings; settings given in their `scan` object must have the
values recorded in the document, otherwise the report stops with an error (see [Report from a scan](../scan/files.md#report-from-a-scan)).

### Settings that moved

These top-level settings are rejected with a message naming their new location.
The analysis settings moved to `scan`, the presentation settings to `report`:

| Former setting | New location |
| --- | --- |
| `missing_values` | `scan.values.null_markers` for markers such as `"N/A"`; empty and whitespace-only cells are missing by default (`scan.values.missing`) |
| `normalization.trim` | `scan.normalization.trim` |
| `normalization.collapse_internal_whitespace` | `scan.normalization.collapse_whitespace` |
| `date_detection` | `scan.detectors.date` |
| `type_inference.minimum_confidence` | `scan.types.minimum_confidence` |
| `enum_detection` | `scan.detectors.enumeration`: `maximum_distinct_values` is `maximum_distinct`, and `minimum_row_count` is `minimum_values`, which counts present values, not rows |
| `value_examples.candidate_sample_size` | `scan.limits.max_samples` |
| `value_examples.random_seed` | `scan.random_seed` |
| `preview_rows` | `scan.records.sample.edge` and `report.row_sample` |
| `string_analysis` | `report.string_analysis` |
| `report.string_analysis.very_short_max_length`, `short_max_length`, `medium_max_length` and `long_max_length` | `scan.classification.<same key>`: the Text type they decide is written in the scan |
| `value_examples` (other than the two below) | `report.value_examples` |

## Output settings

```json
{
  "output": {
    "json_indent": false
  }
}
```

- `output.json_indent`: `false` by default. The scan document and the report
  JSON are then written without indentation, on one line, which is about 60%
  smaller. With `true` they are indented by two spaces and each sample entry
  stays on one line (about half the size of a fully indented file), which is
  easier to read when debugging. Only the layout changes: both forms hold the
  same document. The execution history (`executions.json`) and the Inspect
  file are always indented, being small and meant to be read.

## Deep settings

The top-level `deep` object configures the second pass of `tabalyst scan
--deep` and of `tabalyst report`, in [Add histograms and exact medians](../scan/deep.md).
It is not part of the `scan` object: changing it never makes a stored scan stale.

```json
{"deep": {"bins": 50, "bin_strategy": "sample_quantile"}}
```

| Setting | Default | Meaning |
| --- | --- | --- |
| `deep.bins` | `100` | Number of bins of the histogram of a numeric field that is not counted per integer, and of the numbers of amounts, percentages and quantities (at most, for those in bins whose width is a power of two). From 2 to 1,000 |
| `deep.mode` | `auto` | What `tabalyst report` does about the second pass. `auto`: the planner adds the analyses that are useful and cheap. `off`: none, for a script that must read each file once. `force`: the same as `--deep`, with its confirmation. `tabalyst scan --deep` is an explicit request and runs whatever the mode |
| `deep.pearson.max_columns` | `50` | Numeric columns of a dataset explored for pairs, from 2 to 200. The least present columns beyond it are left out, and the plan counts them |
| `deep.pearson.max_work` | `1000000` | Pairs times rows compared by the exploration of the row sample. It lowers the number of columns explored when `max_columns` is not enough |
| `deep.pearson.max_candidates` | `20` | Pairs the plan lists at most, the best first. A forced second pass takes them all |
| `deep.pearson.automatic_pairs` | `8` | Pairs `tabalyst report` picks by itself at most; `0` picks none. A pair is picked when the lower end of its 95% interval is 0.45 or more |
| `deep.pearson.explore_min_pairs` | `30` | Rows both columns need in the sample for the exploration to score a pair |
| `deep.pearson.min_pairs` | `10` | Rows both columns need in the file for a coefficient to be defined. Changing it computes the pairs again |
| `deep.pearson.rank_bins` | `64` | Bins per column of the grid the rank (Spearman) correlation is read from; `0` turns the rank correlation off, in the result and in the rating of the pairs. From 4 to 1,024. Changing it computes the pairs again |
| `deep.crosstab.max_categories` | `30` | Categories a table keeps as rows, the most frequent; the others are `other`. From 2 to 200. Changing it computes the tables again |
| `deep.crosstab.max_classes` | `12` | Classes of a length, a prefix or a value, `other` included, from 3 to 50. Changing it computes those tables again |
| `deep.crosstab.max_distinct` | `100` | Most distinct values a column may have to be a category, from 2 to 1,000 (the scan lists the frequencies of 100 values by default, `scan.limits.max_listed_frequencies`) |
| `deep.crosstab.prefix_length` | `2` | Characters of a prefix, from 1 to 8. Changing it computes the prefix tables again |
| `deep.crosstab.examples` | `3` | Rows kept as examples for each cell of a table, from 0 to 10 |
| `deep.crosstab.max_exception_cells` | `20` | Cells of exceptions a table lists at most, the largest first, from 1 to 1,000; the result says whether that was all of them. Changing it computes the tables again |
| `deep.crosstab.rule_purity`, `deep.crosstab.rule_support` | `90`, `30` | A category gives a candidate rule when at least `rule_support` counted rows are in its dominant class and `rule_purity` percent of them |
| `deep.crosstab.max_columns`, `deep.crosstab.max_work` | `50`, `1000000` | Columns explored for tables, and tables times rows coded by the exploration of the row sample |
| `deep.crosstab.max_candidates`, `deep.crosstab.automatic_tables` | `20`, `2` | Tables the plan lists at most, and `tabalyst report` picks by itself at most (`0` picks none). A table is picked when its corrected Cramér's V is 0.45 or more |
| `deep.crosstab.explore_min_rows` | `30` | Rows a table needs in the sample for the exploration to score it |
| `deep.stats.max_categories` | `30` | Categories the numbers are described for, the most frequent; the others are `other`. From 2 to 200. Changing it computes those analyses again |
| `deep.stats.bins` | `50` | Bins every category is counted in, placed as `deep.bin_strategy` says, from 2 to 1,000. Changing it computes those analyses again |
| `deep.stats.max_distinct` | `100` | Most distinct values a column may have to be a category, from 2 to 1,000 |
| `deep.stats.max_columns`, `deep.stats.max_work` | `50`, `1000000` | Columns explored for numbers by category, and pairs times rows compared by the exploration of the row sample |
| `deep.stats.max_candidates`, `deep.stats.automatic_stats` | `20`, `2` | Pairs the plan lists at most, and `tabalyst report` picks by itself at most (`0` picks none). A pair is picked when the square root of its corrected correlation ratio is 0.45 or more |
| `deep.stats.explore_min_rows` | `30` | Rows a pair needs in the sample for the exploration to score it |
| `deep.shape.max_values` | `100000` | Different numbers of a column counted exactly by `numeric_shape`. Beyond, the numbers go on in bins: counts, extremes and decimals stay exact, the quartiles and the outliers of Tukey are bracketed. From 1 to 10,000,000. Changing it computes the shape again |
| `deep.drift.max_tracked` | `1000` | Most different values a column may have for `position_drift` to follow the values themselves along the file; the scan must list all of them with their counts, and it lists 100 by default (`scan.limits.max_listed_frequencies`). Beyond, only the missing values are followed. From 2 to 10,000. Changing it computes the drift again |
| `deep.drift.max_listed` | `12` | Values listed with their counts in each tenth of the file, the most frequent first; the others are summed up. From 1 to 100. Changing it computes the drift of the columns whose values are followed again |
| `deep.missing.max_columns` | `100` | Columns of a dataset that lack a value that `missing_matrix` accepts; a dataset with more is left out, because the pairs grow with the square of the columns. From 2 to 1,000. Changing it computes the matrix again |
| `deep.missing.max_listed` | `10` | Partners listed for a column, the ones that lack a value most often with it. From 1 to 1,000. Changing it computes the matrix again |
| `deep.date_order.min_share` | `0.99` | Share of the sampled rows with both dates where the first date must be on or before the second for a pair of date columns to be counted by `date_order`. From 0.5 to 1. Changing it changes the pairs the plan lists, not a result |
| `deep.date_order.max_listed` | `10` | Broken records listed in a `date_order` result, in file order. From 1 to 1,000. Changing it computes the order again |
| `deep.date_order.max_candidates` | `20` | Pairs of date columns at most that the plan lists. From 0 to 1,000 |
| `deep.date_order.automatic_pairs` | `20` | Pairs at most that `tabalyst report` takes by itself. From 0 to 1,000 |
| `deep.date_order.explore_min_pairs` | `30` | Sampled rows with both dates a pair needs to be scored |
| `deep.date_order.max_columns`, `deep.date_order.max_work` | `50`, `1000000` | Date columns of a dataset and pairs times rows the exploration of the sample accepts; the least present columns are left out and counted |
| `deep.arrays.max_lengths` | `10000` | Different lengths `array_profile` counts one by one; a JSON field whose arrays spread over a wider range (longest minus shortest) is left out. From 2 to 100,000. Changing it computes the lengths again |
| `deep.structure.max_variants` | `1000` | Sets of keys `structure_variants` tracks, each counted exactly from its first object; objects with another set are summed up and the result says it is not complete. From 2 to 10,000. Changing it computes the sets again |
| `deep.structure.max_listed`, `deep.structure.max_keys` | `10`, `30` | Sets listed, the most frequent first (from 1 to 100), and keys named in a list (from 1 to 200). Changing them computes the sets again |
| `deep.texts.min_length` | `80` | Characters a value must reach for its field to be a field of texts, for `text_profile` and `fingerprint_distinct`; a field whose values the scan sampled as long texts is one too. From 1 |
| `deep.texts.max_listed` | `10` | Repeated texts `fingerprint_distinct` lists, by digest and count, the most repeated first. From 1 to 100. Changing it computes the fingerprints again |
| `deep.sensitive.enabled` | `false` | Lets the second pass count the columns whose exposure is `mask` or `hide`: the exact distinct count of both, and for `mask` the masks of the values and their classes (`sensitive_forms`), never a value. Off, such a column is left out of every analysis. Changing it changes the plan |
| `deep.sensitive.min_count` | `5` | The floor of `sensitive_forms`: a mask or a class that fewer values take is summed up with the others, and no figure is given about it. From 2 to 1,000. Changing it computes the masks again |
| `deep.sensitive.max_listed`, `deep.sensitive.max_tracked` | `20`, `10000` | Masks listed (from 1 to 1,000) and tracked, each counted exactly from its first occurrence; values with another mask are summed up and the result says it is not complete (from 10 to 100,000). Changing them computes the masks again |
| `deep.datetime.infer_order` | `true` | Read the ambiguous dates (`03/04/2020`) in the order that the unambiguous dates of the column prove when they all give the same one (day-month or month-day), and count them with the others. `false`, or both orders in the column, keeps them ambiguous. An order of `detectors.date.ambiguous_order` always wins. Changing it computes the distribution over time and the parts again |
| `deep.datetime.min_evidence` | `3` | The fewest unambiguous dates that must prove the order (day-month or month-day) for `deep.datetime.infer_order` to read the ambiguous dates that way; below it they stay ambiguous. From 1. Changing it computes the distribution over time and the parts again |
| `deep.datetime.as_of` | none | A calendar date (`YYYY-MM-DD`): `datetime_parts` counts the dates after it. Never the date of the day, so that a result does not change with the clock. Changing it computes the parts again |
| `deep.measures.max_groups` | `20` | Currencies or units of a field of amounts, percentages or quantities that get metrics of their own, the most frequent first; the others are counted together in `other`. From 1 to 1,000. Changing it computes the extraction again |
| `deep.measures.max_values` | `100000` | Different pairs of a currency or unit and a number counted exactly in a field. Beyond, every group goes on in bins: counts, sums and extremes stay exact, the median and quantiles are estimated. From 1 to 10,000,000. Changing it computes the extraction again |
| `deep.patterns.table_bytes` | `65536` | Memory of the table that counts the values of a facet of a pattern family, per facet and field (128 bytes a cell). When it is full the most frequent values are kept and the result says it is limited. From 1,024 bytes to 64 MiB. Changing it computes the analysis again |
| `deep.patterns.distinct_bytes` | `1048576` | Memory of the set that counts the distinct values of the patterns of a field read from the file. Beyond it their distinct values are a lower bound (`at_least`). From 1,024 bytes to 512 MiB. Changing it computes the analysis again |
| `deep.residuals.max_listed` | `20` | Values listed per source and state in the values that patterns and detectors leave out, the most frequent first. From 1 to 1,000. Changing it computes the analysis again |
| `deep.residuals.max_tracked` | `10000` | Distinct values counted per source and state; the occurrences of the values met after that are only counted. From 1 to 1,000,000 |
| `deep.residuals.max_value_length` | `100` | A value longer than this many characters is counted and never listed. From 1 to 10,000 |
| `deep.residuals.max_detectors` | `3` | Detectors replayed per field, the one that read the most values first. From 1 to 20 |
| `deep.residuals.records` | `false` | Give the first record of each value even when the scan holds every distinct value, which makes the second pass read the source |
| `deep.duplicates.max_listed`, `deep.duplicates.max_tracked` | `20`, `10000` | Repeated values listed, the most repeated first (1 to 1,000), and repeated values whose count is tracked (1 to 1,000,000); the occurrences of the others are only counted |
| `deep.duplicates.records` | `false` | Give the first record of each repeated value even when the scan holds every distinct value, which makes the second pass read the source |
| `deep.bin_strategy` | `linear` | `linear`: bins of equal width between the exact minimum and maximum. `sample_quantile`: inner edges at the quantiles of the sample kept by the scan, for a very skewed distribution; it falls back to `linear` when the sample is too small, and says so |

The counts per bin are exact with either strategy.

## Smart settings

The top-level `smart` object configures the plan of a smart sample, in [Plan the
analyses a scan could add](../scan/plan.md#smart-sample-plan), and the sample that
[`tabalyst sample --smart`](../sample/index.md#cover-rare-cases-with-a-smart-sample)
builds from it. It is not part of the
`scan` object or of `deep`: changing it never makes a stored scan or a second-pass
result stale.

```json
{"smart": {"reserve_share": 0.3, "weights": {"cap": 12}}}
```

| Setting | Default | Meaning |
| --- | --- | --- |
| `smart.max_enum_values` | `100` | Most distinct values a column may have to get one target per value. From 1 to 10,000 |
| `smart.max_exact_values` | `500` | Most distinct values a column may have to get one target per value when the second pass counted every value exactly (above `smart.max_enum_values`, which limits the values the first pass lists). From 1 to 10,000 |
| `smart.near_share` | `0.08` | Share of the rows asked for that the groups of near values may take at most (the typos of a category, see [Sample](../sample/index.md#cover-rare-cases-with-a-smart-sample)), from 0 to 1. The groups are shared between the columns in turn, and a sample too small for its mandatory targets gets none. 0 turns them off |
| `smart.near_groups_per_column` | `10` | Groups of near values at most in one column, from 0 to 1,000. 0 turns them off |
| `smart.near_groups` | `100` | Groups of near values at most in the dataset, from 0 to 100,000. 0 turns them off. The plan counts the groups the three limits leave out among the targets it left out |
| `smart.numeric_bins` | `10` | Bins of equal width between the minimum and the maximum of a numeric column, from 2 to 100. A column with fewer than three possible bins gets none |
| `smart.candidates_per_target` | `2` | Rows the selection holds in memory for each target, from 1 to 3 |
| `smart.reserve_share` | `0.2` | Share of the rows asked for that is kept for ordinary rows, from 0 to 0.9. It gives way to mandatory targets |
| `smart.worst_rows` | `3` | Rows with the most weight of anomalies at once that the sample keeps whatever their targets, from 0 (off) to 100. A sample gives them at most a twentieth of its size |
| `smart.max_targets` | `10000` | Targets the plan keeps at most, the heaviest first; the plan counts the others |
| `smart.max_candidate_bytes` | `67108864` | Memory the candidate rows may take, in bytes of source text |
| `smart.weights.gain`, `smart.weights.floor`, `smart.weights.cap`, `smart.weights.unknown_rarity` | `1`, `0.000001`, `20`, `0.5` | A target weighs `min(cap, base * (1 + gain * rarity))`. The rarity goes from 0 (the target covers every row) to 1 (it covers a share of `floor` or less); it is `unknown_rarity` when the frequency is not known |
| `smart.weights.base.*` | see below | The base weight of each kind of target |

The base weights are `confirmed_issue` 10, `candidate_anomaly` 6, `value` 5,
`relation_exception` 5, `pattern` 4, `extreme` 4, `signal` 3, `bin` 2 and
`missing` 6 (the empty cells of a column), `remark` 5 (a remark of the scan that
may be valid: cells trimmed or with collapsed whitespace) and `character` 5 (an unexpected
character in a column) `exact_value` 2 (a value of a column the second pass counted exactly, above `smart.max_enum_values`) and `near_value` 4 (a frequent value with typos next to it); the rarity of the target raises them. A weight never falls
when the target gets rarer or when its base rises, and never passes `cap`.

## Sample settings

```json
{
  "csv": {
    "encoding": "utf-8-sig",
    "delimiter": ","
  }
}
```

- `csv.encoding`: source-file encoding for `tabalyst sample`. The default
  accepts UTF-8 with or without a BOM; `cp1252` is useful for some
  Windows-produced files.
- `csv.delimiter`: single-character separator, a comma by default.

## Scan settings

`tabalyst scan`, `tabalyst report` and their Python functions read the `scan`
object of each configuration file. The complete object with its defaults is:

```json
{
  "scan": {
    "csv": {"encoding": "utf-8-sig", "delimiter": ","},
    "json": {
      "collections": null, "discovery_max_depth": 3,
      "flatten": {"enabled": true, "separator": ".", "max_depth": null},
      "arrays": {"mode": "preserve"}
    },
    "excel": {"dataset_path": null, "header_row": null},
    "errors": {"policy": null, "max_locations": 10},
    "values": {
      "null_markers": [],
      "null_markers_case_sensitive": true,
      "missing": ["absent", "null", "empty", "blank", "marker"]
    },
    "normalization": {
      "nfc": true, "trim": true, "collapse_whitespace": true,
      "casefold": true, "strip_accents": true
    },
    "limits": {
      "max_fields": 10000, "max_depth": 64, "max_record_observations": 100000,
      "max_line_bytes": 16777216,
      "max_distinct_per_field": 100000, "max_tracked_values": 2000000,
      "max_stored_value_length": 1000, "max_listed_frequencies": 100,
      "max_samples": 10000, "max_long_samples": 100,
      "long_preview_chars": 200, "max_samples_per_length": 100,
      "max_length_strata": 64, "max_sample_memory": 536870912,
      "max_special_characters": 256, "max_distinct_characters": 1024,
      "max_variant_groups": 100,
      "max_variants_per_group": 20, "max_evidence_examples": 10,
      "max_tracked_records": 2000000, "max_listed_records": 10
    },
    "records": {
      "duplicates": true,
      "sample": {
        "rows": 1000, "edge": 50, "cell_chars": 200,
        "max_bytes": 16777216
      }
    },
    "types": {"minimum_confidence": 0.95},
    "classification": {
      "very_short_max_length": 5, "short_max_length": 20,
      "medium_max_length": 50, "long_max_length": 255
    },
    "detection": {
      "minimum_share": 0.95, "warmup_values": 10000, "probe_interval": 100,
      "rare_share": 0.001
    },
    "detectors": {"number": {"enabled": true}},
    "patterns": [],
    "exposure": {"sensitive_values": "mask"},
    "pattern_inference": {
      "enabled": true, "max_values": 10000,
      "max_families": 16, "max_patterns_per_family": 32,
      "max_patterns": 128, "max_depth": 3,
      "max_value_length": 64, "min_distinct": 2
    },
    "observations": {"enabled": true, "max_items": 1000},
    "random_seed": 42
  }
}
```

Scans and reports do not read the top-level `csv` settings: set the delimiter
and encoding in `scan.csv`, or pass `--delimiter` and `--encoding`.

### Layers and merge rules

From lowest to highest priority: built-in defaults, for a JSON source with no
Inspect file the collection that [Inspect](../inspect/json.md)
detects, the `scan` object of each `--config` file in the order given, the
`config` of the [Inspect file](../inspect/format.md#config) beside the source, then
`--delimiter`, `--encoding` and `--collection`. For a workbook, the layers are
the same with `excel.dataset_path` in place of `json.collections`.

- Objects merge key by key, including `detectors.<id>`: a file that sets
  `{"detectors": {"number": {"enabled": false}}}` keeps the other number
  settings.
- Lists replace the previous list entirely, such as `null_markers`,
  `patterns` or `collections`.
- Unknown keys are errors.
- `null` is accepted only where a setting allows it; there is no syntax to
  delete a setting.

The scan document embeds the effective configuration and its SHA-256
(`config_sha256`). A stored scan is reused only when the source content, that
configuration, the version of Tabalyst and the version of the pattern discovery
that found its `derived.patterns` are all the same. A second-pass result that
validates patterns is reused only for the same discovery. A stored scan whose
fingerprint no longer matches its configuration, such as one written before a
setting existed, is out of date and scanned again.

### Sources and errors

- `csv.encoding`, `csv.delimiter`: as for reports. The first record is the
  header.
- `json.collections`: for JSON files, a list of absolute collection paths such
  as `"$.customers[]"` or `"$.customers[].orders[]"`. Paths must end with `[]`,
  be unique and not contain one another, and are stored in canonical spelling
  (`$["orders"][]` becomes `$.orders[]`). `null` means that no collection is
  named: `tabalyst scan` and `tabalyst report` then use the collection that
  [Inspect](../inspect/json.md) selects, or stop with exit code `2`
  when it cannot select one. Only `tabalyst.scan()` turns `null` into automatic
  discovery of every array. For a JSONL file it is `null` or `["$[]"]`. A file
  that lists `json.collections` is shared by sources of every format, so it is
  ignored for JSONL and Excel sources in a mixed batch.
- `excel.dataset_path`: for Excel files (`.xlsx`, `.xlsm`), the table to read: a
  sheet, `"$.Sales"`, or a named table of a sheet, `"$.Sales.Orders"`. A name that
  is not a plain identifier is quoted, `"$[\"Q1 2026\"]"`. It is stored in canonical
  spelling. `null` means that no table is named: `tabalyst scan` and
  `tabalyst report` then use the table that
  [Inspect](../inspect/excel.md) selects, or stop with exit code `2` when it
  cannot select one. `tabalyst.scan()` has no automatic mode: a workbook without
  `excel.dataset_path` is an error.
- `excel.header_row`: the 1-based row of a sheet that holds the header, instead
  of the detected one; `null` (default) detects it in the first 50 rows. A strict
  integer from 1.
- `json.discovery_max_depth`: how deep Inspect, and automatic discovery, look
  for arrays under a root object.
- `json.flatten`: how nested objects become fields. `enabled` (default `true`),
  `separator` (default `.`) joins the keys of a field name such as
  `address.city`; it is one character that is not a letter, digit, `_`,
  whitespace or one of `[ ] " \ $`. `max_depth` (default `null`, no limit) counts
  segments from the root of the record, a key or `[]` each: `address` is 1,
  `address.city` is 2, `orders[].amount` is 3. A container (object or array)
  at that depth is kept whole as a complex value and its content is not
  analyzed: nothing is lost, no warning is raised, and the report shows it as a
  column of type `complex`. `enabled: false` is a depth of 1. The separator
  changes only the names shown: a key holding it is written `["a/b"]`, and
  dataset paths such as `$.customers[]` always use `.`. This is not
  `limits.max_depth`, which protects the reader and truncates with a warning.
  Content below the flatten depth is not read for duplicate keys.
- `json.arrays` (`mode`, only `preserve`): arrays never add records. `ignore`
  and `explode` are refused.
- `errors.policy`: `null` (default) is the default of the source format,
  `strict` for CSV and JSON, `tolerant` for JSONL. `strict` stops at the first
  malformed record, such as a CSV record with the wrong number of fields, a JSON
  object with a duplicate key or a JSONL line that is not valid JSON. `tolerant`
  excludes such records, counts them and marks the scan `partial`. Invalid
  syntax in a JSON file, undecodable text and unreadable files stop the scan in
  both policies.
- `errors.max_locations`: how many record locations each diagnostic lists.

The `json.collections`, `json.flatten`, `json.arrays` and `errors.policy`
settings are the ones an [Inspect file](../inspect/format.md#config) edits, under
the names `structure.dataset_path`, `flatten`, `arrays` and `errors.policy`.
For a workbook, they are `excel.dataset_path` and `excel.header_row`, under the
names `structure.dataset_path` and `structure.header_row`.

### Values and missing values

- `values.null_markers`: strings that stand for a missing value, such as
  `"N/A"`, compared after trimming surrounding whitespace.
- `values.null_markers_case_sensitive`: set to `false` to match `n/a` too.
- `values.missing`: the categories counted as missing: `absent` (the key or
  column does not exist in a record), `null`, `empty` (`""`), `blank`
  (whitespace only) and `marker`. Every component stays listed in the result.

### Normalization

Each stage can be turned off. They run in this order: `nfc` (Unicode
composition), `trim`, `collapse_whitespace`, `casefold` and `strip_accents`.
The first three produce the analytical value used by listings and detectors;
all stages count the values they change and group variants that become equal,
such as `Montréal` and `MONTREAL`. Raw values are never modified.

### Limits

Limits bound memory and output size. A measure that reaches a limit is marked
`limited` in the result, never estimated. Values above the maximum are
rejected before the scan starts.

| Setting | Default | Maximum | When reached |
| --- | --- | --- | --- |
| `max_fields` | 10,000 | 1,000,000 | New field paths of a dataset are counted but not analyzed. |
| `max_depth` | 64 | 1,000 | Deeper JSON content is counted but not analyzed. |
| `max_record_observations` | 100,000 | 100,000,000 | The record is an error, or excluded under `tolerant`. |
| `max_line_bytes` | 16,777,216 (16 MiB) | 268,435,456 (256 MiB) | JSONL only: a longer line is not parsed. It is an error, or excluded under `tolerant`. The memory needed to parse a line is about 7 to 13 times its size. |
| `max_distinct_per_field` | 100,000 | 50,000,000 | Distinct values of the field stop being stored; frequencies and cardinality become limited. |
| `max_tracked_values` | 2,000,000 | 500,000,000 | Distinct values stored for the whole scan; the largest field is released first. |
| `max_stored_value_length` | 1,000 | 1,000,000 | Longer values are counted, not stored; a small sample of them keeps a preview and a digest. |
| `max_listed_frequencies` | 100 | 100,000 | Most frequent values listed per field. |
| `max_samples` | 10,000 | 100,000 | Size of the sample of distinct values the scan keeps per field, with their exact counts. |
| `max_long_samples` | 100 | 10,000 | Size of the sample of long texts (above `max_stored_value_length`) kept per field; 0 keeps none. |
| `long_preview_chars` | 200 | 1,000,000 | Characters of a long text kept as a preview. It never exceeds `max_stored_value_length`. |
| `max_samples_per_length` | 100 | 10,000 | Distinct values kept per tracked length by the [samples by length](../scan/format.md#samples-by-length); 0 turns them off. |
| `max_length_strata` | 64 | 10,000 | Lengths tracked per field by the samples by length; the others are summed in `other`; 0 turns them off. |
| `max_sample_memory` | 536,870,912 (512 MiB) | 1,099,511,627,776 | Bytes, by a cost model, that the samples of the whole scan may take; a sample is cut to fit and says so (`requested_k`, `reason`). |
| `max_top_characters` | 20 | 1,000 | Characters and emoji sequences the [character map](../scan/format.md#character-map) lists per field; 0 turns the map off. |
| `max_special_characters` | 256 | 100,000 | Distinct special characters the [character profile](../scan/format.md#character-profile) lists per field; above it the inventory is `limited` and lists none; 0 turns it off. |
| `max_distinct_characters` | 1,024 | 1,114,112 | Distinct characters the character profile counts exactly per field; above it the count is `limited`. |
| `max_variant_groups` | 100 | 100,000 | Normalization variant groups listed per field. |
| `max_variants_per_group` | 20 | 10,000 | Variants listed per group. |
| `max_evidence_examples` | 10 | 1,000 | Example values per detector state. |
| `max_tracked_records` | 2,000,000 | 500,000,000 | Distinct records stored for the whole scan to find duplicates, about 80 bytes each; later records are still compared with the stored ones, so duplicate counts become lower bounds. |
| `max_listed_records` | 10 | 10,000 | Record numbers listed per records block. |

`max_distinct_per_field` cannot exceed `max_tracked_values`, and
`max_samples` cannot exceed `max_distinct_per_field`. When `max_samples` is not set, it is
10,000 or `max_distinct_per_field` when that is lower; the scan document
records the value in force. Counters, statistics and detector coverage stay
exact after a limit is reached.

The two settings have different jobs, and they are not the settings of the
report:

| Setting | Tool | Meaning |
| --- | --- | --- |
| `scan.limits.max_distinct_per_field` | Scan, and Report through the scan it runs | Distinct values counted exactly; beyond it the cardinality is `limited` |
| `scan.limits.max_samples` | Scan | Size of the sample of distinct values kept in the scan document |
| `report.value_examples.kept_per_column` | Report | Sample values the report keeps per column, at most 1,000 (default 100): the smallest priorities of the scan sample, so a subset of it |
| `report.value_examples.*` | Report | What the report shows and how it picks examples from the values it kept |
| `report.row_sample.start`, `middle`, `end` | Report | Rows of the row sample the report keeps and shows: the first, the interior rows of smallest priority, the last (0 to 1,000 each, default 10, never more than the scan kept) |

### Records

- `records.preview` no longer exists: the first records are the start of the
  row sample (`records.sample.edge`). Setting it is an error that names its
  replacements.
- `records.duplicates`: set to `false` to skip duplicate detection, which
  stores one digest per distinct record, up to `limits.max_tracked_records`.
  The duplicate count is then `disabled`.
- `records.sample`: the [row sample](../scan/format.md#row-sample) of each dataset.
  `rows` is its total size (default 1,000, up to 100,000; 0 turns it off), `edge` the
  number of first and of last rows (default 50; `2 * edge` cannot exceed `rows`, so the
  middle has `rows` - 2 * `edge` rows), `cell_chars` the characters kept per cell
  (default 200) and `max_bytes` the budget, by a cost model, of the rows kept by the
  whole scan (default 16 MiB, from 1 MiB). A larger sample or wider cells need a larger
  budget; when it is exceeded the middle shrinks and the document says so.

### Types and interpretations

- `types.minimum_confidence`: share of values that must agree for a field to
  get a technical type such as `integer` or `date`, otherwise `mixed`.
- `detection.minimum_share`: share of the values that a detector must match to
  become a candidate interpretation of the field.
- `detection.warmup_values`: default 10,000, up to 1,000,000. The first
  distinct values of each field go through every detector. A detector that
  recognized none of them, not even as invalid or ambiguous, is then skipped
  for the other values of the field, which count as `not_tested` in its
  coverage. `number` and `date` are never skipped. A field with fewer
  distinct values is always analyzed by every detector. Set it to `0` to test
  every value with every detector, as before this setting existed.
- `detection.rare_share`: default 0.001, from 0 to 1. A detector that
  recognized at most this share of the warm-up values, and none of those in
  the second half of the warm-up, is skipped too: its reactions were rare and
  have stopped. The default allows 10 values of a 10,000-value warm-up. A
  detector still recognizing values at the end of the warm-up stays, as in a
  sorted column where matches become frequent, and so does a sensitive
  detector that found only invalid values. `0` skips only the detectors that
  recognized nothing.
- `detection.probe_interval`: default 100, up to 1,000,000. After the
  warm-up, about one distinct value in this number, chosen by a hash of the
  value, still goes through every detector. The scan reports a
  `detector_skipped_reacted` warning, meaning that the counts of a skipped
  detector for the field are incomplete, when it recognizes one of these
  probes after recognizing nothing in the warm-up, or, for a rare detector,
  when it recognizes at least 10 probed values, more often than
  `detection.rare_share` allows. `0` disables probes.

A detector skipped after the warm-up may miss rare values that appear later
in the file, including sensitive ones such as an email address in a comment
column: such a value would not be masked. Set `detection.warmup_values` to
`0` when every sensitive value must be found.

### Text length bounds

`classification` holds the four bounds that name the Text types of a column:
Very short up to `very_short_max_length` characters, Short up to
`short_max_length`, Medium up to `medium_max_length`, Long up to
`long_max_length` and Very long above. The type is decided on the exact median
of the lengths of the present values, not on the maximum. The bounds must be
whole numbers of at least 1 and strictly increasing.

The `report.string_analysis` section reads the same bounds on the maximum
length (see [String analysis](#string-analysis)). They are scan settings because
the Text type is written in the scan document: changing one changes the scan
configuration, so a stored scan is stale and the source is scanned again. They
were `report.string_analysis` settings before; the old keys are refused with
their new place (see [Settings that moved](#settings-that-moved)).

### Detectors

Every detector has `enabled` (default `true`) and the settings below. Other
detector ids are errors.

| Detector | Settings and defaults |
| --- | --- |
| `number` | `conventions`: `["dot", "comma"]`, the decimal separators accepted; `ambiguous_convention`: `null`, or `dot` or `comma` to read values such as `1,234` one way; `infer_convention`: `true`, read them in the convention the other numbers of the column prove; `min_evidence`: 3, the fewest numbers that must prove it. |
| `date` | `orders`: `["YMD", "MDY", "DMY"]`; `separators`: `["-", "/", "."]`; `ambiguous_order`: `null`, or `MDY` or `DMY` to read values such as `02/03/2025` one way; `month_languages`: `["en", "fr"]`. |
| `boolean` | `pairs`: `[["true", "false"], ["yes", "no"], ["y", "n"], ["oui", "non"], ["vrai", "faux"]]`. |
| `enumeration` | `minimum_values`: 500; `maximum_distinct`: 49; `case_sensitive`: `true`. |
| `email` | `max_tracked_domains`: 10,000; `max_listed_domains`: 20. |
| `url` | `schemes`: `["http", "https", "ftp"]`; `www`: `true`, accept addresses starting with `www.`; `max_tracked_hosts`: 10,000; `max_listed_hosts`: 20. |
| `phone` | `regions`: `["nanp", "fr"]`; `nanp` covers Canada and the United States. |
| `postal_code` | `regions`: `["ca", "us"]`, Canadian postal codes and ZIP codes. |
| `currency` | `conventions`, `ambiguous_convention`, `infer_convention` and `min_evidence`, as for `number`. |
| `percentage` | `conventions`, `ambiguous_convention`, `infer_convention` and `min_evidence`, as for `number`. |
| `quantity` | `conventions`, `ambiguous_convention`, `infer_convention` and `min_evidence`, as for `number`; `max_tracked_units`: 10,000; `max_listed_units`: 20. |
| `uuid` | No other setting. |
| `ip_address` | `versions`: `["ipv4", "ipv6"]`. |

`ambiguous_convention` and `ambiguous_order` resolve ambiguous values. Without
them, the scan reads ambiguous numbers such as `1,234` in the convention that at
least `min_evidence` other numbers of the same column prove, when none proves the
other; a decimal comma proven that way also makes `1.250` read as 1250. The
`currency`, `percentage` and `quantity` settings do not change the scan, which
counts no number of an amount: the second pass applies them to the numbers of the
values with a unit, from the evidence of the same detector (`1,250 Kg`,
`$1.250`). Ambiguous dates are read by the evidence of their column in the
second pass only (`deep.datetime.infer_order`).

### Patterns

`patterns` adds your own detectors, reported as `pattern:<id>`:

```json
{
  "scan": {
    "patterns": [
      {
        "id": "customer_number",
        "regex": "C-\\d{4}",
        "description": "Customer number",
        "accepts": ["string"],
        "sensitive": false,
        "max_input_length": 256
      }
    ]
  }
}
```

- `id`: 1 to 64 letters, digits, `_` or `-`, unique.
- `regex`: a Python regular expression of at most 1,000 characters that must
  match the whole value.
- `accepts`: native types tested, among `string`, `integer`, `number` and
  `boolean`; default `["string"]`.
- `sensitive`: `true` masks the fields where the pattern matches.
- `max_input_length`: longer values are not tested; default 256, at most
  10,000.

At most 200 patterns. Regular expressions run without a timeout: use only
patterns you trust, since some expressions can take a very long time on some
values.

### Pattern inference

After a scan, the structural patterns of each text field are inferred from its
samples (see [Inferred patterns](../scan/format.md#inferred-patterns)). They are
not the configured patterns above.

| Setting | Default | Maximum | Meaning |
| --- | --- | --- | --- |
| `pattern_inference.enabled` | `true` | | `false` skips the inference and leaves `derived` out of the document. |
| `pattern_inference.max_values` | 10,000 | 20,000 | Distinct values of a field that the discovery reads. |
| `pattern_inference.max_families` | 16 | 1,024 | Most families per field; the others are counted in `other`. |
| `pattern_inference.max_patterns_per_family` | 32 | 1,024 | Most patterns per family; the other lengths are counted in a table. |
| `pattern_inference.max_patterns` | 128 | 1,024 | Most patterns and nodes per field; the nodes of the lowest gain go first. |
| `pattern_inference.max_depth` | 3 | 4 | Levels of the tree under a family: the pattern, the nodes that read the first or last characters of a token, then the nodes that depend on them. |
| `pattern_inference.max_value_length` | 64 | 1,000 | Longer values do not take part and are counted as excluded. |
| `pattern_inference.min_distinct` | 2 | 1,000 | Distinct values a field needs to be assessed for patterns. |

### Observations

After a scan, the observations, quality issues and limits of its facts are
written in `observations` (see
[Observations and limits](../scan/format.md#observations-and-limits)).

| Setting | Default | Maximum | Meaning |
| --- | --- | --- | --- |
| `observations.enabled` | `true` | | `false` leaves `observations` out of the document. |
| `observations.max_items` | 1,000 | 100,000 | Most observations, and most limits, that are listed; the counts of the summaries stay complete. |

### Sensitive values and sampling

- `exposure.sensitive_values`: how values of sensitive fields (email
  addresses, phone numbers, IP addresses and sensitive patterns) appear in the
  result. `show` (default) keeps them; `mask` replaces letters with `A` or `a`
  and digits with `9`; `hide` removes the values and keeps the counts. Sample
  files always keep the values of the source.
- `exposure.detector_keys`: `aggregate` (default) publishes the keys that the
  `email`, `phone` and `postal_code` detectors declare (extension and domain,
  region and area code, postal area) even on a masked or hidden field, as counts of
  at least 5 occurrences with no example or row of the sample; `mask` withholds them
  on such a field.
- `random_seed`: seed of the hash that orders the value samples, an integer from
  0 to 2^64 - 1, so that two scans of the same file with the same settings are
  identical.
