---
title: JSON profile
description: Structure of the JSON profile written by tabalyst report, a Scan document with a report block, with its fields, column projections, the findings it carries and format versioning.
---

Each `tabalyst report` run writes a JSON profile next to the HTML report, with
the same name: `orders.html` comes with `orders.json`. For a JSON source, the
default names are `orders.report.html` and `orders.report.json`, so the profile
never replaces the source. The profile holds the
complete analysis result; the HTML report is rendered from it. Use it to read
Tabalyst results from scripts or other tools.

The profile is written without indentation unless `output.json_indent` is `true`
in the [configuration](../reference/configuration.md#output-settings).

The profile is a [scan document](../scan/format.md) with an added `report`
block. Everything the scan measured stays where the scan puts it, at the same
paths (`datasets[].fields[]`, `source`, `config`, `scope`, `diagnostics`), and
the `report` block adds what the report presents: its settings, the summary
of each dataset and the projections of its columns. A tool that reads scan
documents reads the profile too: see [Reading the base](#reading-the-base).

The format is **experimental**: it can change incompatibly between releases.
Always check `format_version` and `format_revision` first. This page describes
format `0.2.0`, revision `3`.

## Example

A shortened profile for a five-row `orders.csv`:

```json
{
  "format": "tabalyst.report",
  "format_version": "0.2.0",
  "format_revision": 3,
  "engine": { "...": "versions of the engine and the detectors" },
  "status": "complete",
  "run": { "...": "start, duration and timings of the scan" },
  "source": {
    "format": "csv",
    "name": "orders.csv",
    "size_bytes": 274,
    "sha256": "7d426449...",
    "encoding": "utf-8-sig",
    "csv": { "delimiter": ",", "...": "header, quote, BOM, line ending" }
  },
  "config": { "...": "the effective scan settings" },
  "config_sha256": "e3b0c442...",
  "scope": { "records_read": 5, "records_analyzed": 5 },
  "datasets": [
    {
      "id": "rows",
      "kind": "table",
      "record_count": 5,
      "fields": [ { "id": "column_3", "display": "amount", "...": "facts" } ]
    }
  ],
  "diagnostics": [],
  "report": {
    "generated_at": "2026-10-06T12:00:00Z",
    "generator": { "name": "tabalyst", "version": "0.7.0" },
    "processing_seconds": 0.0098,
    "config": { "string_analysis": {}, "value_examples": {} },
    "base_scan": {
      "format": "tabalyst.scan",
      "format_version": "0.2.0",
      "format_revision": 3,
      "engine_version": "0.7.0",
      "source_sha256": "7d426449...",
      "config_sha256": "e3b0c442...",
      "facts_sha256": "91ab0c55..."
    },
    "datasets": [
      {
        "id": "rows",
        "kind": "table",
        "summary": {
          "row_count": 5,
          "column_count": 6,
          "missing_count": 2,
          "duplicate_row_count": 1
        },
        "date_summary": { "...": "present when a column contains dates" },
        "columns": [
          {
            "id": "column_3",
            "name": "amount",
            "path": "amount",
            "position": 3,
            "inferred_type": "mixed",
            "type_counts": { "number": 3, "text": 1 },
            "type_confidence": 0.75,
            "missing_count": 1,
            "missing_percent": 20.0,
            "distinct_count": 3,
            "examples": ["25.00", "12.50", "not available"],
            "classification": {
              "family": "other",
              "type": "mixed",
              "basis": "fallback",
              "state": "established",
              "traits": [],
              "evidence": [
                {
                  "source": "technical_type",
                  "id": "mixed",
                  "role": "supports",
                  "scope": {
                    "population": "present_values",
                    "of": 4,
                    "partial": false,
                    "accuracy": "exact"
                  }
                }
              ],
              "alternatives": [],
              "rule_version": 4002
            },
            "detectors": []
          }
        ],
        "structure": null
      }
    ]
  }
}
```

## Top-level fields

| Field | Type | Content |
| --- | --- | --- |
| `format` | string | `"tabalyst.report"`; a scan document has `"tabalyst.scan"` |
| `format_version` | string | Experimental format family, `"0.2.0"` |
| `format_revision` | integer | Revision of the report within the family, increased for each structural or semantic change |
| `engine`, `status`, `run`, `source`, `config`, `config_sha256`, `scope`, `diagnostics` | | The scan base, as in a [scan document](../scan/format.md). `config` is the effective scan configuration, the one recorded in the scan document for a report built with `--scan`. `source` is the file the scan read |
| `datasets` | array | The scan datasets, with their records and fields: the measured facts. The samples of the fields are reduced (see [Reduced samples](#reduced-samples)) |
| `derived` | object | Optional: the [inferred patterns](../scan/format.md#inferred-patterns) of the scan, carried as they are because the reduced samples cannot compute them again |
| `observations` | object | Optional: the [observations and limits](../scan/format.md#observations-and-limits) of the scan, carried as they are. The report reads its quality findings and its limits from them (see [Findings](#findings)) |
| `analyses` | object | Optional: what the [second pass](../scan/deep.md) did for this report (see [`analyses`](#analyses)) |
| `report` | object | What the report adds (see below) |

## `analyses`

The report runs a second pass by itself when the planner finds an analysis useful
and cheap, and `--deep` forces it. This member says what happened and holds the
[second pass document](../scan/deep-format.md) of the run, whole:

| Field | Content |
| --- | --- |
| `mode` | Who decided: `auto` (the planner), `forced` (`--deep`, or `deep.mode` set to `force`) or `off` (`deep.mode` set to `off`) |
| `outcome` | `ran` (analyses were computed), `reused` (the stored results of an earlier run were enough), `nothing_selected`, `disabled`, `unavailable` (analyses that need the source could not read it) or `failed` (an automatic second pass met an error and the report goes without it) |
| `reason` | Why, for `disabled`, `unavailable` and `failed`; a sentence |
| `deep` | The second pass document: its `plan` lists every candidate analysis with the decision on it and its reason (kept, already answered by the scan, or left out), and `analyses` holds the results, each with its `status` and `reason`. A candidate of the plan holds `id`, `analyzer`, `dataset`, `field`, `display`, `partner` (for a pair of columns), `applicability` and `selection`; its costs, execution and parameters are in the second pass document written beside the scan. `plan_id` is the identity of that whole plan |

The results include the correlation of the pairs of numeric columns that the plan kept
(`pearson_correlation`, see [Correlation between two columns](../scan/deep.md#correlation-between-two-columns)):
an entry of `analyses` names both fields (`field` and `partner`) and the plan has a
`relations` member that says which columns were explored. The tables of a category against
a feature (`category_crosstab`, see [A category against a feature](../scan/deep.md#a-category-against-a-feature-of-another-column))
are there too, with `partner` the column of the feature and `relations.tables` in the plan, and so are the
numbers of a column by category (`category_stats`, see [The numbers of a column by
category](../scan/deep.md#the-numbers-of-a-column-by-category)), with `partner` the numeric column and
`relations.stats` in the plan. The shape of the numbers (`numeric_shape`, see [The shape of the
numbers](../scan/deep.md#the-shape-of-the-numbers)) and the parts of the dates (`datetime_parts`, see [The
parts of the dates](../scan/deep.md#the-parts-of-the-dates)) are entries of `analyses` too, and so are the
drift of a column along the file (`position_drift`, see [A column along the file](../scan/deep.md#a-column-along-the-file))
and the columns that miss a value together (`missing_matrix`, see [Columns that miss a value
together](../scan/deep.md#columns-that-miss-a-value-together)), as are the lengths of the arrays and the sets of
keys of the objects of a JSON file (`array_profile` and `structure_variants`, see [Arrays and sets of keys in
JSON](../scan/deep.md#arrays-and-sets-of-keys-in-json)), the words and lines of long texts and their fingerprints
(`text_profile` and `fingerprint_distinct`, see [Long texts](../scan/deep.md#long-texts)) and the masks and classes of
a masked column (`sensitive_forms`, see [Sensitive columns without a
value](../scan/deep.md#sensitive-columns-without-a-value)), which never holds a value of that column.

A report built with `--scan` reads no source: the analyses that need it are
`skipped` with the reason `source_not_read`. A report written before the second
pass existed has no `analyses`, and its HTML has no Insights or Second pass section. The
Insights cards are derived from `analyses` when the HTML is rendered; they are not stored.

## `report`

| Field | Content |
| --- | --- |
| `generated_at` | UTC date and time of the report (ISO 8601) |
| `generator` | `name` (`tabalyst`) and `version` of the Tabalyst that wrote the report |
| `processing_seconds` | Scan and profile time, in seconds; for a report built from a scan document with `--scan`, the scan duration recorded in the document plus the time to read it and build the profile |
| `config` | The presentation settings: `string_analysis` (`length_distribution_max_length` and `examples_per_length`; the length bounds are in the root `config.classification`), `value_examples` and `row_sample`. The analysis settings are the root `config`. See the [configuration](../reference/configuration.md) |
| `base_scan` | The identity of the scan base the report holds (see below) |
| `datasets` | One projection per dataset shown, identified by the dataset `id` (see below) |

A change of the presentation settings changes `report.config` and nothing
else: it never starts a new scan.

## `base_scan`

| Field | Content |
| --- | --- |
| `format`, `format_version`, `format_revision` | The format of the scan base, `tabalyst.scan` at its own revision: the root `format_revision` is the report's |
| `engine_version` | Version of the engine that scanned |
| `source_sha256`, `config_sha256` | SHA-256 of the source file and of the scan configuration |
| `facts_sha256` | SHA-256 of the facts of the base: the document without `run` and without the contents of the samples, of their strata by length and of the row samples. A report and the scan it comes from have the same value, whatever their presentation settings or sample sizes |

## Reading the base

`tabalyst.scan_document.load_base(path)` reads a scan document or a report and
returns the same `ScanResult` model: for a report it ignores `report`, and it
refuses a document whose base is not at the current revision or does not match
its `base_scan`. `load_document(path)` also says whether the file is a scan or
a report and what it can still be used for. A report can be sent alone: it is
read and rendered without the scan or the source.

## Reduced samples

The report keeps fewer sample values than the scan: at most
`report.config.value_examples.kept_per_column` distinct values per field (100 by
default), the ones of smallest hash priority: a subset of the scan's with the
same exact counts, and the same whatever the size of the scan sample. Each
`values.samples` block says how many it lists, `kept`, out of how many the scan
sampled, `of`. A scan has `kept` equal to `of`. The
[samples by length](../scan/format.md#samples-by-length) of a field keep their
lengths, counts and accuracy, and no values: each stratum has `kept` 0.
The [cases of the observed rules](../scan/format.md#cases-of-the-observed-rules)
keep their counts and no texts: each class has `kept` 0 and an empty `listed`.

The [row sample](../scan/format.md#row-sample) of a dataset (`records.sample`)
keeps its header and the rows `report.config.row_sample` asks for: the first
`start` rows, the last `end` rows and the `middle` rows of the interior with the
smallest priorities, 10 of each by default, an exact subset of the scan's rows.
`kept` says how many it lists and `of` how many the scan sampled.

A report with `kept` below `of` renders and is read like any scan base, but it
cannot be the input of a computation that reads samples: use the scan
document of the source for it.

## `report.datasets`

The projections of the scan datasets, in the order the report shows them. They
are summaries and choices of presentation computed from the facts of
`datasets[].fields[]`: a column here has the `id` of the scan field it
presents. A CSV file has one dataset, `rows`, whose records are the rows of the file;
so has an Excel workbook, whose rows are those of the table analyzed. A
JSON file has one dataset per collection analyzed, such as `$.customers[]`,
usually one: the collection selected by [Inspect](../inspect/json.md)
or named with `--collection`. A JSONL file has one dataset, `$[]`. Reports
built by the commands have no `$` dataset for the rest of the document. See the
[scan format](../scan/format.md) for the datasets of a scan.

| Field | Type | Content |
| --- | --- | --- |
| `id` | string | Dataset identifier: `rows`, `$` or a collection path such as `$.customers[]` |
| `kind` | string | `table` (CSV), `document` or `collection` (JSON) |
| `summary` | object | Dataset-level counts (see below) |
| `date_summary` | object or `null` | Dataset-level date counts, when at least one column contains date values |
| `columns` | array | One profile per column, in file order for CSV and in order of discovery for JSON |
| `structure` | object or `null` | Paths of a JSON dataset, containers included (see below); `null` for CSV files |
| `table` | object | What the Summary table and the overview cards print for the dataset: `error_count`, `issue_count`, `observation_count` (columns by flag), `signals` (one entry per finding code and unit, with the columns behind its total) and `quality` (columns with Errors, with Issues only and with no finding) |

In a JSON dataset, a column is a field that holds strings, numbers, booleans
or nulls, named by its path: `email`, `address.city`, `orders[].total`.
Objects and arrays themselves are not columns, except the ones kept whole at
the `scan.json.flatten.max_depth` limit, which are columns of type `complex`.
A row is a record of the dataset.

## `summary`

Counts over the whole dataset:

- size: `row_count` (records), `column_count`, `cell_count` (the places a
  value could be: one per row and column for CSV; for JSON, the occurrences
  of each field plus the objects where it is absent);
- missing values: `missing_count`, `missing_percent`;
- normalization: `trim_count`, `collapse_internal_whitespace_count`;
- structure: `duplicate_row_count`, `empty_row_count`, `empty_column_count`,
  `constant_column_count`;
- `duplicate_row_status`: `complete`; `limited` when more distinct rows than
  `scan.limits.max_tracked_records` were read, `duplicate_row_count` then
  being a lower bound; or `disabled` when `scan.records.duplicates` is
  `false`, `duplicate_row_count` then being `null`;
- column families: `numeric_column_count`, `date_column_count`,
  `string_column_count`;
- type distributions: `inferred_type_counts`, `inferred_type_percents`,
  and, by classification, `type_family_counts`, `type_family_percents`,
  `type_counts` and `type_percents`: columns by family (key `identifier`)
  and by type (key `identifier/unique_id`).

Percentages are numbers from 0 to 100.

## `columns`

Each column profile always contains:

| Field | Content |
| --- | --- |
| `id` | Stable identifier from the position, such as `column_3`. Use it rather than `name`, which can be blank or repeated |
| `name` | Header text for CSV; the field path for JSON |
| `path` | Field path as displayed by the scan: the header text for CSV, a path such as `orders[].total` for JSON |
| `position` | Position in the file for CSV, in order of discovery for JSON, starting at 1 |
| `inferred_type` | `empty`, `complex`, `boolean`, `integer`, `number`, `date`, `text` or `mixed`. A column of dates is `date` even with several formats or ambiguous values. `complex` is a JSON column whose present values are all objects or arrays kept whole at the flatten limit; `type_counts` then counts `object` and `array` |
| `type_counts` | Number of present values of each type |
| `type_confidence` | Share of present values accepted by the inferred type, from 0 to 1. For `mixed` columns, the share of the largest type family; `null` for `empty` columns |
| `type_error_count`, `type_error_percent` | Values outside the inferred type; `null` for `mixed` columns. The percentage is over the analyzable (non-missing) values of the column |
| `missing_count`, `missing_percent` | Missing cells; for JSON, also the objects where the field is absent. The percentage is over the cells of the column (the rows of a CSV; for JSON, the occurrences of the field plus the objects where it is absent) |
| `normalization` | Values changed by each normalization stage and the variant groups (see below); missing cells are not counted |
| `distinct_count` | Number of distinct values after normalization, even for a masked column; `null` when a scan limit stopped the count |
| `classification` | The family and type of the column, with `basis`, `state`, `traits`, `evidence`, `alternatives` and `rule_version`. It is the `classification` of the scan field (see [Classification](../scan/format.md#classification)), refined by the second pass when it supplies a fact the scan lacked: an `identifier/id` whose distinct count the scan could not complete becomes `identifier/unique_id` when the exact distinct count proves it (see [Exact distinct count](../scan/deep.md#exact-distinct-count)). A report without a usable second pass carries the classification of the scan |
| `summary` | What the Summary table and the previews say about the column, built with the report and holding codes and numbers, never a sentence: `findings` (`missing`, `errors` and `issues`, each finding with its code, class, count, unit, population, share, accuracy and examples already through the exposure, and each list with its evaluation state and the checks behind it), `overview` (the profile and the facts of its sentence), `details` (representative values and measures), `values` (the inline examples and the value occurrences, complete or sampled, see `selection`), `finding_details` (the evidence behind the Issues of the Findings table: `variants`, the groups of spelling variants, `dates`, the pairs of formats that fit the same ambiguous values with the unambiguous values per day-month order and the formats read without doubt, and `patterns`, the dominant pattern and the minority ones with examples taken from a sample (absent for a masked or hidden column, which has no pattern), `lengths`, the dominant length and the other lengths of the column with their counts and example texts of each length, read from the scan's cases (the texts are masked or withheld by the exposure; the lengths and counts are not; `complete` says the examples are every distinct text of the length), `whitespace`, the cells each whitespace stage changed, the exact cells of each kind (`kinds`: `leading`, `trailing`, `repeated`, with `occurrences` and `complete`) and example texts of each kind from the scan's cases (the value keeps its whitespace), and `types`, the composition of a mixed column by technical type with the type it comes closest to (codes and counts, no value); a member is absent when the column has no observation of its rule), `flags` and, for an identifier column only, `identifier_uniqueness` (`null` for any other column): whether the ID is unique across all rows and after row deduplication, with the repetitions that exact copies of whole rows explain and those that remain between distinct records, the evidence behind each figure and the proofs refused. It holds codes and exact integers, never a sentence or an ID value, and does not change the classification or `identifier.repetition` (see [revision 5](profile-changelog.md#version-020-revision-5)). The words are written when the report is rendered |
| `exposure` | `mask`, `hide` or `show` for a sensitive column, the way its values appear in `summary` and the rows of the data sample; `null` otherwise |
| `detectors` | The detectors that recognized values of the column, in scan order (see below); empty when none did |

`summary.values.selection` is `complete` when all available frequencies are
listed. A primary `enumeration` keeps this complete list even above
`report.config.value_examples.full_distribution_max_distinct`, if the Scan frequency measure
is complete. Otherwise the profile uses a bounded diverse or random sample.

The statistics of a column are not repeated here: a column page and the HTML
report read them where the scan keeps them, in the field of `datasets` with the
same `id`.

| Statistics | Where |
| --- | --- |
| Numbers: `minimum`, `maximum`, `mean`, `median` (limited when a scan limit stopped it) | `numeric` of the field |
| Dates: valid, ambiguous and invalid counts, formats and ambiguity evidence | the `date` entry of `detectors` of the field, and `temporal` |
| Text: length statistics and distribution | `string_lengths` of the field |
| Presence, native types, missing breakdown, first and last values | `presence`, `native_types`, `missing` and `values` of the field |

The report shows ambiguous dates as the scan found them: the evidence per
day-month order (`DMY`, `MDY`) is shown and never applied, and the order is
resolved only by `scan.detectors.date.ambiguous_order`. The second pass reads them by the evidence of the
column in its own results (`datetime_parts`, `temporal_distribution`), which the Insights section says; the counts of the
scan do not change.

## `normalization`

What the scan's normalization did to the present values of the column. Raw
values are never changed.

| Field | Content |
| --- | --- |
| `trim_count`, `trim_percent` | Values changed by trimming surrounding whitespace. The percentage is over all the cells of the column, missing ones included, so it is lower than the share among text values |
| `collapse_internal_whitespace_count`, `collapse_internal_whitespace_percent` | Values changed by collapsing repeated internal whitespace, counted after trimming; same denominator as `trim_percent` |
| `stages` | One item per stage, in order: `raw`, `nfc`, `trim`, `collapse_whitespace`, `casefold`, `strip_accents` (see below) |
| `variant_group_count` | Normalized values written in at least two raw ways; `null` unless `variant_group_status` is `complete` |
| `variant_group_status` | `complete`, `limited` when a scan limit stopped the count and some stage changed a string, or `not_applicable` without text values |
| `variant_groups` | The largest groups (`scan.limits.max_variant_groups`), each with its comparison `key`, its occurrence `count`, `distinct_count` (raw spellings), `variants` (`value` and `count`, at most `scan.limits.max_variants_per_group`) and `truncated`; masked for a sensitive column, empty when hidden |
| `variant_groups_truncated` | `true` when more groups exist than are listed |

Each item of `stages` has:

| Field | Content |
| --- | --- |
| `stage` | Stage name; `raw` describes the values as read |
| `enabled` | `false` when the stage is turned off in `scan.normalization` |
| `changed_count`, `changed_percent` | Values the stage changed, given the previous enabled stage; `null` for `raw` and disabled stages |
| `distinct_count` | Distinct values after the stage; `null` unless `distinct_status` is `complete`. A stage that changed nothing has the count of the previous one, also when the scan limited it (see [Normalization stages](../scan/format.md#normalization-stages)) |
| `distinct_status` | `complete`, `limited`, `not_applicable` (no values) or `disabled` |

A variant group is an analytical equivalence, such as `Montréal`,
`montreal` and `MONTREAL`, not proof that the values mean the same thing.

## `detectors`

Each item describes what one scan detector recognized in the column. The
detectors that matched values or found ambiguous or invalid ones are listed,
as well as failed ones.

| Field | Content |
| --- | --- |
| `id` | Detector id, such as `email`, `date` or `pattern:order_id` |
| `status` | `complete`, or `failed` when the detector stopped with an error |
| `primary` | `true` for the scan's primary interpretation, the only detector that reached `scan.detection.minimum_share` |
| `eligible_count` | Values the detector could examine |
| `matched_count`, `matched_percent` | Values recognized, and their share of the eligible values |
| `ambiguous_count` | Values with more than one reading, such as `01/02/2026` |
| `invalid_count` | Values with the right shape but an impossible content, such as `2026-02-30` |
| `formats` | Formats found, each with `format`, `count` and `percent` of the eligible values |
| `coverage` | Complete Scan coverage, including tested, not tested and not matched counts; `null` for a failed detector |
| `evidence` | Bounded exposed examples for matched, ambiguous, invalid and not matched values; `null` for a failed detector |
| `details` | Detector-specific, exposure-controlled Scan metadata |
| `adaptive` | Adaptive detection skip and probe metadata, when applicable |

## Findings

The projections hold no list of problems: the report reads the findings of the
scan, which the document carries as it is. They are the same ones in the
`observations` block and in the pages of the HTML report.

- **Quality issues and remarks.** `observations.items` lists what the scan found,
  each with a `rule`, a `status` (`confirmed_issue`, `candidate_anomaly` or
  `informational`), the `field` and `dataset` it concerns, a `count` out of `of`
  and its `accuracy` (`exact`, `lower_bound` or `sample`). A column has quality
  issues when an item about its `field` is a confirmed issue or a candidate
  anomaly; a remark, such as missing values, is not an issue. See
  [observations and limits](../scan/format.md#observations-and-limits).
- **Limits.** `observations.limits` lists what the scan could not establish:
  `measure` (its place in the scan result, such as `values.cardinality`,
  `numeric.median` or `structure.paths`), `reason` (such as `distinct_limit`,
  `global_budget`, `value_too_long`, `field_limit`, `record_budget` or
  `memory_budget`), `limit` and `lower_bound`, a proven minimum when there is
  one. A limited measure is never presented as exact.
- **Diagnostics.** `diagnostics`, at the root, are the technical events of the
  scan, such as excluded records: `code`, `level`, `message`, `count`, `dataset`
  (`null` for the whole scan), `field` and up to `scan.errors.max_locations`
  `locations`.
- **Structure counts.** `datasets[].structure.untracked_observations` counts the
  values under paths beyond `scan.limits.max_fields` and
  `depth_truncated_observations` the values deeper than `scan.limits.max_depth`,
  counted but not analyzed.
- **Rows.** `datasets[].records.sample.rows` lists the rows the report shows, each
  with its logical `record` number, its `origins` (`start`, `middle`, `end`) and
  its `values` by field id.

Without an `observations` block (`scan.observations.enabled` is `false`) the
report says that the findings are not computed; it does not rebuild them.

## `structure`

The shape of a JSON dataset; `null` for CSV files.

| Field | Content |
| --- | --- |
| `record_types` | Number of records of each native type, such as `{"object": 60}` |
| `path_count` | Number of paths; `null` when `path_status` is `limited` |
| `path_status` | `complete`, or `limited` when the dataset has more paths than `scan.limits.max_fields` |
| `max_depth_seen` | Depth of the deepest analyzed value |
| `fields` | One item per path, in order of discovery, containers included (see below) |

Each item of `fields` has:

| Field | Content |
| --- | --- |
| `id` | Scan field id |
| `path` | Path from the record, such as `orders[].total` |
| `depth` | Number of path segments: `orders[].total` has depth 3 |
| `parent` | Path of the parent field, `null` at the record root |
| `native_types` | Occurrences of each JSON type: `object`, `array`, `string`, `integer`, `number`, `boolean`, `null` |
| `occurrences` | Values found at the path |
| `parent_type` | `record`, `object`, or `array` for array items |
| `parent_count`, `present_count`, `absent_count` | Parents that could hold the field, those that do and those that do not; `absent_count` is `null` for array items |
| `present_percent` | Share of the parents holding the field; `null` for array items, which count elements |
| `collection` | For an array analyzed as its own dataset, the id of that dataset |
| `arrays` | For arrays: `count`, `empty_count`, `minimum_length`, `maximum_length`, `mean_length` and `item_count`; `null` otherwise |
| `column` | `true` when the field is also listed in `columns` |

## Large integers

Counters and numeric statistics are JSON integers written with all their digits,
even beyond 2^53 (9,007,199,254,740,992). The HTML report writes them exactly
and compares them exactly. A tool that reads the file with `JSON.parse` in
JavaScript rounds integers beyond 2^53: use a parser that keeps large integers
(for example by reading them as `BigInt`), or read the file in a language with
arbitrary-size integers.

## Versioning

- `format_version` names the experimental format family. The current value is
  `"0.2.0"`.
- `format_revision` increases for each structural or semantic change. It does
  not change for report styling or performance improvements.
- Revisions can be incompatible, and no migration is provided. See the
  [JSON profile changelog](profile-changelog.md).

The profile contains values from the source file, in `examples` and
`value_profile` of the report, and in the samples and the row sample of the base;
only sensitive columns are masked. Share it as
you would share the data.
