---
title: Findings catalog
description: Every Error, Issue and Information finding that Tabalyst Report states about a column, with its code, what it counts, when it applies, its detail and its limits, as the JSON profile carries them.
---

A **finding** is what a rule found in a column: a count in one unit, out of a
population, with its accuracy. Tabalyst has three classes of finding. An
**Error** is a value that a deterministic rule proves invalid. An **Issue** is
an ambiguity or a deviation worth a look, never proof of an error. An
**Information** is a fact about a column. There is no Warning class.

Each finding has a stable `code`. This page lists them all, as the
[JSON profile](json-profile.md) carries them. The HTML report is one reading of
the same data and its wording can change; the codes and the members below do
not depend on it.

```text
report.datasets[].columns[].summary.findings
  missing   Missing positions of the column
  errors    Errors: findings, state and checks behind them
  issues    Issues: findings, state and checks behind them
```

## The codes at a glance

Twelve codes produce a finding in `errors` or `issues`. Two more state a fact.

| Code | Class | Counts | Unit | Out of | Detail member |
| --- | --- | --- | --- | --- | --- |
| `temporal.invalid_calendar` | Error | Dates that do not exist | occurrences | date values | none |
| `semantic.invalid` | Error | Values failing the shape or the syntax of their type | occurrences | values the detector tested | none |
| `type.outside_family` | Error | Values that are not numbers in a numeric column | occurrences | present values | none |
| `temporal.ambiguous_date` | Issue | Dates that fit two day-month orders | occurrences | date values | `dates` |
| `number.ambiguous` | Issue | Numbers with more than one reading | occurrences | values the detector tested | none |
| `categorical.case_variants` | Issue | Groups of spellings of one text | groups | no population | `variants` |
| `pattern.minority` | Issue | Distinct values in a rare pattern | distinct values | distinct values | `patterns` |
| `length.minority` | Issue | Values of a rare length | occurrences | text values | `lengths` |
| `type.mixed` | Issue | Values outside the closest technical type | occurrences | present values | `types` |
| `identifier.repetition` | Issue | Repetitions beyond the first occurrence | occurrences | present values | none |
| `text.surrounding_whitespace` | Issue | Values with whitespace around the text | occurrences | text values | `whitespace` |
| `text.repeated_whitespace` | Issue | Values with whitespace repeated inside | occurrences | text values | `whitespace` |
| `presence.empty_column` | Information | Positions of an empty column | positions | positions | none |
| `values.constant_column` | Information | Positions of a constant column | positions | positions | none |

A finding in the JSON has: `code`, `cls` (`error`, `issue`), `field`, `count`,
`unit`, `population` (its `kind` and `size`), `share` (numerator, denominator,
percent), `accuracy`, `status`, `basis` (the ids of the observations behind
it), `examples` with `examples_state`, and `overlaps`. A count is exact unless
its `accuracy` says `lower_bound` (a limit stopped it), `sample` or
`estimated`. A share has its own accuracy and is `null` when the population
is unknown.

```json
{
  "code": "temporal.ambiguous_date",
  "cls": "issue",
  "field": "column_5",
  "count": 10857,
  "unit": "occurrences",
  "population": {"kind": "occurrences", "size": 99994},
  "accuracy": "exact",
  "status": "detected",
  "basis": ["o4"],
  "examples_state": "shown"
}
```

Two findings are never added together unless one proves they cover the same
values; `overlaps` lists the codes proven to overlap and is empty otherwise.
The dataset totals only sum findings of one code counted in one unit.

## Errors

An Error needs a column whose classification is `established`. On a column
whose type is only a `candidate` or is `undetermined`, the same fact is stated
as an Issue with the same code, and the preview of the finding says so.

### `temporal.invalid_calendar`

- **Category:** Temporal columns (Date, Datetime, Time).
- **Counts:** the values the date detector reads as a date and rejects: an
  impossible calendar date (`2025-02-30`), an impossible time (`25:00`) or
  offset, mixed separators (`2025/01-15`) and a component of the wrong width.
- **Source:** the `date` detector, `coverage.invalid`, out of its eligible
  values. A value that is not date-shaped is not counted.
- **Detail:** none; the examples come with the finding.
- **Limits:** the reasons are not split. A date that passes can still be wrong.
  Narrowing `scan.detectors.date.orders` makes a date of an order left out
  count as invalid.

### `semantic.invalid`

- **Category:** columns classified as Email, Phone, Postal code, URL, IP
  address or UUID. One code covers all six; the detector is named in `basis`.
- **Counts:** values that do not have the shape of the type, or have it and
  fail its syntax. For example `K0J S9` in a postal code column, a space in
  the local part of an email, an area code no phone number
  has, a Canadian postal code with a letter Canada Post does not use, a port
  above 65,535, an octet above 255, or a non-hexadecimal digit in a UUID.
- **Source:** the detector of the type of the column, `coverage.invalid` plus
  `coverage.not_matched`. A
  detector of another type that finds values in the column is not a constraint
  on it.
- **Detail:** none.
- **Limits:** syntax only, no code is looked up. The type is established by the
  detector and the name of the column, so a value outside it counts.

### `type.outside_family`

- **Category:** columns classified and typed Integer or Number.
- **Counts:** present values that are not numbers: a word, a symbol or a
  currency code. The decimals of an Integer column are numbers and are not
  counted.
- **Source:** `technical_type.outside_count`, exact over the values read.
- **Detail:** none.
- **Limits:** says which values are not numbers, not what they should have
  been. Date, Boolean and Text columns have no check: an impossible date has
  its own code, and a Text column has no family to fall outside of.

## Issues

An Issue needs no established classification: it states what the Scan found,
on whatever column it found it. An ambiguous date in a Text column is an Issue.

### `temporal.ambiguous_date`

- **Counts:** dates that two configured day and month orders both read as
  valid, such as `03/04/2024`.
- **Source:** the observation `ambiguous_dates`, out of the date values.
- **Detail** (`finding_details.dates`): `ambiguous_count`; `candidates`, the
  pairs of formats that fit the same values with their counts; `readings`, the
  unambiguous values per day-month order; `formats`, the formats read without
  doubt, each with its order and count; `more_candidates` and `more_formats`
  when the lists are bounded (six each). No example: a format is a shape.
- **Settings:** `scan.detectors.date.ambiguous_order` (`DMY` or `MDY`) reads
  the values one way, and the Scan then raises no observation.
  `deep.datetime.infer_order` lets the second pass read them by the evidence
  of the column. See [Configuration](../reference/configuration.md#detectors).
- **Limits:** an ambiguous date is not wrong. Tabalyst never guesses the order.

### `number.ambiguous`

- **Counts:** numbers whose separators allow more than one reading, such as
  `1,234`.
- **Source:** the `number` detector, `coverage.ambiguous`, out of its eligible
  values. A count behind a partly tested detector is a lower bound.
- **Detail:** none.
- **Settings:** `scan.detectors.number.ambiguous_convention`,
  `infer_convention` and `min_evidence`.
- **Limits:** an ambiguous number is not wrong. Tabalyst does not guess.

### `categorical.case_variants`

- **Counts:** groups of values that differ only by case, accents or spacing,
  such as `Montréal` and `MONTREAL`. The unit is groups, never the occurrences
  inside them, and there is no population, so no share.
- **Source:** the observation `variant_groups`, built by the normalization
  stages.
- **Detail** (`finding_details.variants`): the largest groups, each with its
  comparison key, its occurrence count, its distinct spellings and their
  counts, the most frequent first; `truncated` flags a bounded list. Masked for
  a masked column, empty for a hidden one.
- **Settings:** `scan.normalization.casefold`, `strip_accents`, `trim`,
  `collapse_whitespace`; `scan.limits.max_variant_groups` and
  `max_variants_per_group`.
- **Limits:** variants are spellings of one text; they do not prove that the
  spellings mean the same thing. The most frequent spelling is the likely
  target of a correction, the others the candidates to review.

### `pattern.minority`

- **Counts:** distinct values written in a pattern that few values share.
- **Rule:** one pattern covers at least 80 % of the distinct values and the
  minority patterns at most 5 % each. These thresholds are constants of the
  version of the rules, not settings.
- **Source:** the observation `minority_pattern` and the inferred patterns.
  The accuracy is `sample` when the discovery read a sample of the distinct
  values (the check is then `partial`, reason `patterns_sample`).
- **Detail** (`finding_details.patterns`): the dominant pattern with its
  distinct values; the minority patterns, largest first (five at most), each
  with its distinct values and up to three examples taken from a sample;
  `more_patterns`. A pattern can show no example, which says nothing about the
  others.
- **Limits:** a rare pattern is a deviation to inspect, not a constraint. A
  masked or hidden column has no pattern and no detail.

### `length.minority`

- **Counts:** text values whose length differs from the one that nearly all the
  values share.
- **Rule:** at least 20 text values, one length holds at least 95 % of them and
  the other lengths at most 5 % together. Lengths count the characters of the
  value after normalization. Two legitimate lengths leave the rule without
  meaning (state `not_applicable`, reason `no_dominant_length`).
- **Source:** the observation `minority_length`, from the exact length
  histogram.
- **Detail** (`finding_details.lengths`): the dominant length, and each other
  length with its count and up to three example texts (five lengths at most;
  `more_lengths`). The texts follow the exposure of the column; the lengths and
  counts do not.
- **Limits:** a minority length may be legitimate. It often betrays a
  malformed value that a pattern absorbed.

### `type.mixed`

- **Counts:** values outside the closest technical type of a column whose
  technical type is `mixed`.
- **Source:** the observation `mixed_types`, out of the present values.
- **Detail** (`finding_details.types`): the composition of the column by
  technical type (`type`, `count`) in descending count, and the type it comes
  closest to. Codes and counts, no example.
- **Limits:** a value of another type may be legitimate. The composition lists
  every type counted, which is not only the values outside the closest type.

### `identifier.repetition`

- **Category:** columns classified in the Identifier family.
- **Counts:** the values present minus the distinct values (`N - D`): the
  occurrences beyond the first one of each identifier. For `A, A, A, B` this
  is 2.
- **Source:** the exact distinct count of the analytical values. When it is not
  exact, the check is `not_assessed` (reason `cardinality_not_exact`). A Unique
  ID has proved its uniqueness and has none.
- **Detail:** none. The card of the [column page](read-report.md#column-page)
  links to the block *Identifier uniqueness*, which separates the repetitions
  that exact copies of whole rows explain from those that remain between
  distinct records.
- **Limits:** it is neither the number of duplicated occurrences nor the number
  of identifiers that repeat. The count is raw: it stays the same whether the
  repetitions come from copied rows or from two different records sharing an ID.
  The decomposition is in `summary.identifier_uniqueness` of the
  [JSON profile](profile-changelog.md); it never turns this Issue into an Error
  and never hides it.

### `text.surrounding_whitespace` and `text.repeated_whitespace`

- **Counts:** text values the `trim` stage changed (whitespace before or
  after the text), and values the `collapse_whitespace` stage changed
  (whitespace repeated inside).
- **Source:** the observations `trimmed_cells` and `collapsed_whitespace`.
  Both are remarks in the Scan; the report states them as Issues. A stage
  turned off gives `not_assessed` (reason `stage_disabled`).
- **Detail** (`finding_details.whitespace`): `stages`, the cells each stage
  changed; `examples` from the sample, by `kind` (`leading`, `trailing`,
  `repeated`), up to three per kind, each value keeping its whitespace. A value
  with two kinds is listed under the first. The counts are per stage, never per
  kind, and the sample says nothing about the examples left out.
- **Settings:** `scan.normalization.trim` and `collapse_whitespace`.
- **Limits:** whitespace is often invisible and says nothing about what the
  value means.

## Information

Two facts about a column are never an Error or an Issue and have no entry in
`errors` or `issues`. They are Scan observations (`empty_column` and
`constant_column`, status `informational`), carried in `observations.items`.

| Code | Meaning |
| --- | --- |
| `presence.empty_column` | Every position of the column is missing |
| `values.constant_column` | Every present value is the same |

## Missing values

Missing positions have their own member, `findings.missing`, separate from
Errors and Issues: a missing value is never an Error or an Issue by itself. It
holds `count`, `unit` (`positions`, or `occurrences` under a JSON array),
`population`, `share`, always exact, and `components`: `absent`, `null`,
`empty`, `blank` and `marker`. The definition of missing is
`scan.values.missing`.

## States of a check

Each list (`errors`, `issues`) has a `state` and `assessments`, one per check
with its `code`, `state`, `accuracy`, `eligible`, `tested` and `reason`. They
tell a clean column from a column a check did not cover.

| State | Meaning |
| --- | --- |
| `detected` | The check ran and found something |
| `none_detected` | The check ran completely and found nothing |
| `partial` | The check covered only part of the values, so a count is a lower bound and nothing is proven absent |
| `not_assessed` | The check was turned off or never ran |
| `not_applicable` | The check has no meaning for this column |
| `failed` | The check raised a diagnostic; it is never an invalid value |

The `reason` of an assessment, when there is one:

| Reason | State | Meaning |
| --- | --- | --- |
| `not_temporal`, `not_semantic_type`, `not_numeric_type`, `not_identifier` | `not_applicable` | The classification of the column is not the one the code concerns |
| `no_values`, `no_text`, `too_few_values`, `no_dominant_length` | `not_applicable` | Nothing to test, or the rule has no meaning on these values |
| `disabled`, `stage_disabled`, `detector_missing`, `no_check` | `not_assessed` | A detector or a stage is off, missing, or no check exists |
| `patterns_unavailable` | `not_assessed` | The Scan inferred no pattern for the column |
| `cardinality_not_exact` | `not_assessed` | The distinct count is not exact |
| `observations_truncated` | `partial` | `scan.observations.max_items` cut the list of observations |
| `observations_unavailable` | `not_assessed` | The Scan holds no observations |
| `patterns_sample` | `partial` | The patterns were inferred on a sample |

The state of a whole list is `detected` when it holds a finding. Otherwise the
checks that apply decide: all in one state give that state, a mix that includes
a completed or partial check is `partial`, and a mix of `failed` and
`not_assessed` is `failed`.

## Examples and sensitive columns

`examples` and the `finding_details` members go through the exposure of the
column before they are written: `shown`, `masked` (merged masks) or `hidden`
(none), in `examples_state`. Counts, lengths, formats and type names describe
shapes and quantities and stay whatever the exposure. An example is cut at 64
characters, with `truncated` set. Examples are taken from the samples the Scan
already holds, never from the source file, so a rare case can have none.

## Observations of the Scan

The findings are built from the Scan's `observations`, carried unchanged in
the profile. The rules of version 2 are below, with the category and status
fixed by the version. See also
[observations and limits](../scan/format.md#observations-and-limits).

| Rule | Category | Status | Scope | Finding code |
| --- | --- | --- | --- | --- |
| `excluded_records` | records | confirmed issue | dataset | none |
| `ambiguous_header` | names | confirmed issue | dataset | none |
| `duplicate_rows` | records | candidate anomaly | dataset | none |
| `mixed_types` | types | candidate anomaly | field | `type.mixed` |
| `type_outliers` | types | candidate anomaly | field | none |
| `ambiguous_dates` | dates | candidate anomaly | field | `temporal.ambiguous_date` |
| `variant_groups` | normalization | candidate anomaly | field | `categorical.case_variants` |
| `minority_pattern` | patterns | candidate anomaly | field | `pattern.minority` |
| `minority_length` | patterns | candidate anomaly | field | `length.minority` |
| `missing_values` | presence | informational | field | `findings.missing` |
| `empty_column` | presence | informational | field | `presence.empty_column` |
| `constant_column` | values | informational | field | `values.constant_column` |
| `trimmed_cells` | normalization | informational | field | `text.surrounding_whitespace` |
| `collapsed_whitespace` | normalization | informational | field | `text.repeated_whitespace` |

Observations without a finding code stay in `observations.items`. The
`type_outliers` observation counts values outside a technical type; the Error
`type.outside_family` reads the technical type itself, and a Date or Boolean
column has no finding for it.

The other codes of a finding (`type.outside_family`, `semantic.invalid`,
`temporal.invalid_calendar`, `number.ambiguous`, `identifier.repetition`) read
detectors, the technical type or the distinct count rather than an
observation.

## Dataset totals

`report.datasets[].table` sums the findings of the columns. `quality` counts
the columns with Errors, with Issues only and with no finding. `signals` has one
entry per code and unit, with `total`, `lower_bound`, and the `columns` behind
it, each with its `count`. See [JSON profile](json-profile.md).
