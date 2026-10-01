---
title: Profile format changelog
description: How report.json identifies its format, and the changes of each format revision.
---

The generated `report.json` identifies its contract with two independent fields:

```json
{
  "format_version": "0.1.0a",
  "format_revision": 10
}
```

`format_version` names the experimental compatibility family. It remains
`0.1.0a` throughout the Tabalyst `0.1.0aX` application series.
`format_revision` is a monotonic integer incremented for meaningful structural or
semantic changes. It does not change for report styling, documentation, performance
improvements, or corrections that preserve the JSON contract.

Beta revisions may be incompatible. No automatic migration is provided yet.

## Revision 1 - 2026-09-18

- Established the first explicitly tracked alpha profile contract.
- Includes dataset/source metadata, effective configuration, quality summary,
  issues, raw preview rows, and global column profiles.
- Column profiles include normalization, inferred and semantic types, errors,
  occurrences, bounded examples, numeric statistics, date analysis, and string
  length statistics.
- Added `format_version` and monotonic `format_revision` identifiers.

## Revision 2 - 2026-09-23

- Materialized per-column `with_issues`, defined as missing values or inferred
  type `mixed`.
- Added dataset-level physical/semantic type distributions and report section
  counts.
- Added dataset-level date aggregates and per-date-column ambiguity summaries.
- Added present counts and percentages to date profiles, numeric ranges, and
  relative/representative string-length values used by the report.

## Revision 3 - 2026-09-27

The report is built on Tabalyst Scan instead of the pandas engine.

- `config` holds the report settings (`preview_rows`, `string_analysis`,
  `value_examples` without `candidate_sample_size` and `random_seed`) and
  `scan`, the complete effective scan configuration. The other former
  settings moved to `scan`.
- Columns of dates with several formats or ambiguous values have
  `inferred_type` `date` instead of `mixed`. `with_issues` is also `true` for
  columns with ambiguous dates, and the new `ambiguous_dates` issue counts them.
- Ambiguous dates are no longer resolved from the other values of the column:
  `ambiguous_order_source` is only `config`, and the new
  `date_profile.ambiguity_evidence` counts unambiguous values per order. Date
  formats include ISO date-times, times and month names; `order` and
  `separator` are `null` for formats that are not numeric dates.
  `date_profile.errors` was removed.
- `semantic_type` is `date` or the id of the scan's primary interpretation
  (`enumeration` instead of `enum`, and new values such as `email`, `phone` or
  `postal_code`). The `enum` block was removed. Enumerations count present
  values, not rows, against their minimum.
- New `exposure` per column; values of sensitive columns are masked by default
  in `examples`, `value_profile` and `preview`, where a hidden value is `null`.
- `distinct_count` and `numeric.median` are `null` when a scan limit stopped
  them; the new `limited_measures` issue lists such columns.
- `type_confidence` is `null` for `empty` columns.
- Numeric statistics cover every number of the column, including decimal
  commas and grouped thousands.
- Normalization counts cover present values only: a whitespace-only cell is
  missing, not trimmed. Distinct values also apply Unicode composition (NFC).
- `string_profile.length_distribution` items no longer have `distinct_count`;
  their examples come from the most frequent and the sampled values.
- Value samples are drawn by the scan (`scan.limits.max_samples`,
  `scan.random_seed`), so sampled examples differ from revision 2.

## Revision 4 - 2026-09-27

The report reads JSON files and lists the detectors of each column.

- The dataset-level fields `summary`, `date_summary`, `columns`, `issues` and
  `preview` moved into the new `datasets` array, one item per dataset with its
  `id` and `kind`. A CSV file has one dataset, `rows`.
- `source` has a new `format` field; `delimiter` is `null` for JSON files.
- Columns have a new `path` and a new `detectors` array: the detectors that
  recognized values, with their counts and formats.
- Preview rows have a new `absent` array: the positions of the JSON fields
  absent from the record.
- In JSON datasets, a column is a field holding scalar values, named by its
  path; absent fields count as missing, and `cell_count` counts the places a
  value could be.

## Revision 5 - 2026-09-28

The report can be built from a scan document, whose records block now holds
the preview and the duplicate rows.

- New `summary.duplicate_row_status`: `complete`, `limited` when more distinct
  rows than `scan.limits.max_tracked_records` were read, in which case
  `duplicate_row_count` is a lower bound, or `disabled` when
  `scan.records.duplicates` is `false`, in which case `duplicate_row_count` is
  `null`.
- The `duplicate_rows` issue message ends with `at least` when the count is a
  lower bound.
- The preview size moved from `config.preview_rows` to
  `config.scan.records.preview`.
- For a report built from a scan document, `processing_seconds` is the time
  to read the document and build the profile.

## Revision 6 - 2026-09-28

The report shows every normalization stage with its variant groups, what the
scan could not measure completely, and the structure of JSON datasets.

- Column `normalization` gains `stages` (`raw`, then `nfc`, `trim`,
  `collapse_whitespace`, `casefold` and `strip_accents`, each with
  `enabled`, `changed_count`, `changed_percent`, `distinct_count` and
  `distinct_status`), `variant_group_count`, `variant_group_status`,
  `variant_groups` and `variant_groups_truncated`.
- New info issue `variant_groups`: values written in several ways that
  normalization compares as equal.
- Each dataset has a new `limits` object: `measures` stopped by a scan limit,
  with their field, reason, limit and proven lower bound;
  `untracked_observations`, `depth_truncated_observations`; and the scan
  `diagnostics` of the dataset and of the whole scan.
- JSON datasets have a new `structure` object: `record_types`, `path_count`,
  `path_status`, `max_depth_seen` and one item per path, containers
  included, with presence per parent and array lengths. It is `null` for CSV
  files.

## Revision 7 - 2026-09-28

The scan behind the report uses adaptive detection by default: on columns
with more than 10,000 distinct values, detectors that recognized none of the
first ones stop testing the others.

- `config.scan.detection` gains `warmup_values` (default 10,000; `0` tests
  every value) and `probe_interval` (default 100).
- Semantic types and inferred types are unchanged on columns where a
  detector matches at least 95% of the values. Counts of rare matches after
  the warm-up may be lower; a `detector_skipped_reacted` warning in the
  dataset `limits.diagnostics` says when a probe found one.
- For a report built from a scan document, `processing_seconds` now adds the
  scan duration recorded in the document to the time to read it and build
  the profile, so it is comparable with a report built from the source.

## Revision 8 - 2026-09-28

The scan behind the report also stops testing rare detectors: those that
recognized at most 0.1% of the first 10,000 distinct values of a column, and
none of the last 5,000.

- `config.scan.detection` gains `rare_share` (default 0.001; `0` keeps the
  behavior of revision 7).
- Semantic types and inferred types are unchanged; only counts of detectors
  with rare matches may be lower. A `detector_skipped_reacted` warning in the
  dataset `limits.diagnostics` says when such a detector recognized probed
  values more often than its warm-up.

## Revision 9 - 2026-09-29

- Column `scan_details` retains bounded Scan evidence for standalone column
  pages: presence, native types, missing components, first/last exposed values,
  string characteristics and lengths, numeric statistics, boolean counts and
  temporal ranges. Values obey the Scan exposure setting.
- Detector entries gain complete coverage, exposed evidence, exposed details
  and adaptive detection metadata when available.
- Primary enumerations include every available frequency even when their
  cardinality exceeds `value_examples.full_distribution_max_distinct`.
- `tabalyst report --details` generates one self-contained HTML page per column
  under the report stem folder. Details are off by default. This changes report
  artifacts, not the meaning of other profile fields.

## Revision 10 - 2026-09-30

- `config.scan` records the rules the scan applied, defaults resolved:
  `config.scan.errors.policy` is `strict` or `tolerant`, never `null`. The
  setting itself accepts `null`, meaning the default of the source format.
- `config.scan.json` gains `flatten` (`enabled`, `separator`, `max_depth`) and
  `arrays` (`mode`). Their defaults keep the previous behavior.
- A JSON field holding only objects or arrays kept whole at the
  `config.scan.json.flatten.max_depth` limit is a column with `inferred_type`
  `complex` and the `object` and `array` counts in `type_counts`. Without a
  flatten limit, containers stay structure and no column changes.
- `source.format` can be `jsonl`, for files ending in `.jsonl` or `.ndjson`.
  Lines excluded under the `tolerant` policy are counted by the existing
  `excluded_records` issue, with their line numbers as `row_numbers`.
  `config.scan.limits` gains `max_line_bytes`.
- The reports built by the commands have one dataset per collection chosen with
  [Inspect](../inspect/format.md) or `--collection`, usually one, and no dataset
  `$` for the rest of the document. The structure of `datasets` does not change.
- Column `path` and `name` of JSON fields are joined with
  `config.scan.json.flatten.separator`.
