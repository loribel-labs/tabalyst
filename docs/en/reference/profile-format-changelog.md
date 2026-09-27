---
title: Profile format changelog
description: How report.json identifies its format, and the changes of each format revision.
---

The generated `report.json` identifies its contract with two independent fields:

```json
{
  "format_version": "0.1.0a",
  "format_revision": 4
}
```

`format_version` names the experimental compatibility family. It remains
`0.1.0a` throughout the Tabalyst `0.1.0aX` application series.
`format_revision` is a monotonic integer incremented for meaningful structural or
semantic changes. It does not change for report styling, documentation, performance
improvements, or corrections that preserve the JSON contract.

Alpha revisions may be incompatible. No automatic migration is provided yet.

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
