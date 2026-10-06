---
title: Native, inferred and semantic types
description: Define every source, inferred and semantic type and how Tabalyst Scan and Report select them.
---

**Tabalyst Scan** records each field's native types, infers a technical type
from present values and chooses a primary interpretation only when one
detector qualifies. **Tabalyst Report** calls the technical type the
**inferred type** and displays the optional **semantic type** in its
[Columns table](../../report/read-report.md#columns).

## Native source types

`native_types` in a Scan field counts values as read, before technical
inference. CSV cells start as strings; JSON and Excel can carry typed values.
The native type alone does not decide the inferred type.

| Native type | Source value |
| --- | --- |
| `string` | Text, including text that may later parse as a number or date. |
| `integer`, `number` | A source number, with `integer` for whole numbers. |
| `boolean` | A source true/false value. |
| `null` | An explicit JSON null. |
| `object`, `array` | JSON containers; they can form paths or stay whole at a flatten limit. |

See `native_types` and `missing` in the [Scan field](../../scan/format.md#fields)
to distinguish source representation from missing-value rules.

## Inferred types

The technical type is chosen from **present** values, after missing values
are removed. Native scalar types contribute directly. Strings are classified
with date, boolean and number rules. Tabalyst chooses the first family that
reaches `scan.types.minimum_confidence`: `integer`, `number` (which also
accepts integers), `date`, `boolean`, then `text`. Otherwise it chooses
`mixed`. The report records `type_counts`, `type_confidence` and
`type_error_count`; its **Analysis settings** gives the effective threshold.

| Inferred type | When it appears | Important distinction |
| --- | --- | --- |
| `empty` | No present analyzable value. | A missing-only field is not inferred as text. |
| `complex` | JSON objects or arrays kept whole at the configured flatten depth. | Their contents are not scalar columns at that depth. |
| `boolean` | Native booleans or technical true/false strings meet the threshold. | The separate boolean detector can recognize more configured word pairs. |
| `integer` | Whole-number values meet the threshold. | A leading-zero identifier stays text. |
| `number` | Numeric values, including integers and non-integers together, meet the threshold. | Configured decimal conventions decide which strings parse. |
| `date` | Calendar dates, including ambiguous day/month forms, meet the threshold. | Date-times and times can match the date detector without becoming calendar-date technical values. |
| `text` | Remaining text values meet the threshold. | Text can still have a semantic type such as `email`. |
| `mixed` | No family reaches the threshold. | No type error count is available because no type was accepted. |

**Error** in the report counts present values outside the accepted inferred
type. Missing values are excluded from its denominator. `mixed` reports the
largest family as confidence but has no type error count.

## Semantic types

Detectors become candidate interpretations when their matched share of
eligible values reaches `scan.detection.minimum_share`. A field gets a
**primary** interpretation only when exactly one detector qualifies. The
report shows `date` for an inferred date field; otherwise it shows the unique
primary detector ID when it adds meaning beyond a technical type. Technical
`number` and `boolean` are not repeated as semantic types. A dash in the
report means no single qualifying meaning, even when detectors have matches.

| Semantic type | Meaning | Scope or condition |
| --- | --- | --- |
| `date` | Date, date-time or time syntax. | A calendar-date inferred field is `date`; the date detector can also be primary for another field. |
| `enumeration` | A bounded set of recurring values. | Field-level rule: enough present values and no more than the configured distinct maximum. |
| `email` | Bare email address syntax. | Does not verify mailbox or domain ownership. |
| `url` | URL syntax and host. | Does not visit the URL or resolve its host. |
| `phone` | Supported phone syntax. | Does not check assigned numbers. |
| `postal_code` | Canadian or US postal-code syntax. | Does not check an assigned address. |
| `currency` | Number with currency symbol or code. | A bare number is not currency evidence. |
| `percentage` | Number followed by `%`. | The parsed value remains as written, such as 12 for `12%`. |
| `quantity` | Number followed by a unit-shaped suffix. | Units are not validated as physical units. |
| `uuid` | UUID text form. | Does not verify that an ID was issued. |
| `ip_address` | IPv4 or IPv6 text form. | Does not check allocation or reachability. |
| `pattern:<id>` | Full-value match to a configured regular expression. | Exists only for a configured pattern. |

Two qualifying detectors do not produce an arbitrary semantic type. Inspect
all their evidence in [Recognized patterns](patterns.md) and in the report's
**Detectors and formats** table.

## Measures by value family

Scan retains measures independently of its final technical type. For example,
a `mixed` field can still have numeric evidence for the values that parsed as
numbers. Report shows its **Numeric analysis** table only for inferred
`integer` and `number` fields with usable statistics, and its **String
analysis** table only for inferred `text` fields. The `--details` column page
also exposes a bounded selection of Scan measures. Always check the measure's
population and status before comparing it with a column's total rows.

### All fields

| Measure | Population and meaning | Where to read it |
| --- | --- | --- |
| Present and missing | Values found at a field versus missing values or absent JSON members under a parent. | Scan `presence` and `missing`; Report **Columns → Missing**. |
| Distinct values | Different present analytical values after enabled Unicode composition, trim and whitespace collapse. | Scan `values.cardinality` and normalization stages; Report **Columns → Distinct**. |
| Frequencies and examples | Occurrence counts for listed values and a bounded sample of distinct values. | Scan `values.frequencies` and `samples`; Report **Examples** and its tooltip. |
| Type confidence and error | Share of present values in the accepted family and count outside it. | Scan `technical_type`; Report **Inferred type** and **Error**. |
| Variant groups | Raw spellings that share a final comparison key after enabled case and accent stages. | Scan `normalization`; Report **Transformations**. |

Distinct counts and frequency lists can be limited; examples are a selection,
not necessarily a complete distribution. A `mixed` field has no type error
count because no family was accepted.

### Numeric values

The Scan `numeric` block measures every accepted numeric value in the field,
including native numbers and text parsed under the configured number rules.
Its `count`, `native_count` and `text_count` identify this population. Report
shows five summary measures for inferred numeric fields:

| Measure | Definition | Availability |
| --- | --- | --- |
| Minimum, Maximum | Smallest and largest accepted numeric value. | Scan and Report. |
| Range | Maximum minus minimum. | Derived in Report from the two bounds. |
| Mean | Sum divided by numeric count. | Scan and Report. |
| Median | Middle numeric value, averaging the two middle values when needed. | Scan measure; `null` in Report when its tracking limit was reached. |
| Sum | Total of accepted numeric values. | Scan and the standalone Report column page. |
| Population variance, standard deviation | Spread around the mean, using the numeric population. | Scan and the standalone Report column page. |
| Positive, negative, zero | Counts of numeric occurrences greater than, less than, or equal to zero. Missing and nonnumeric values are excluded. | Scan and the standalone Report column page. |
| Integral decimals | Decimal values whose numeric value is whole. | Scan and the standalone Report column page. |

The numeric population can be smaller than the field's present-value count if
some values did not parse as numbers. In the Report table, **Distinct** and
**Examples** describe normalized values, not the numeric calculation.
When numeric statistics are complete, `positive + negative + zero` equals
`numeric.count`. For example, `10`, `-2.5`, `0`, `4.5`, and `1.0` yield
3 positive, 1 negative, and 1 zero value. A precision limit can make the
numeric measure unavailable instead of showing partial sign counts.

### Text values and lengths

Scan measures the length of each present **analytical string** after enabled
Unicode composition, trim and internal whitespace collapse. Report's string
profile uses this measure only for an inferred `text` field.

| Measure | Definition | Availability |
| --- | --- | --- |
| Minimum, Maximum length | Shortest and longest observed analytical string, in characters. | Scan `string_lengths`; Report **Min** and **Max**, or **Fixed** if equal. |
| Mean, Median length | Average and middle character count, weighted by occurrences. | Scan and Report; Report leaves these cells blank when **Fixed** already gives the one length. |
| Fixed length | Minimum equals maximum; the shared length is displayed. | Derived in Report, not a claim about the field's meaning. |
| Length distribution | Exact occurrence count for each observed length. | Scan histogram; Report **Lengths** only when the maximum fits `string_analysis.length_distribution_max_length`. |
| Distinct lengths | Number of different lengths observed. | Report JSON profile even when the HTML length distribution is omitted. |
| Length class | `very_short`, `short`, `medium`, `long` or `very_long`, chosen from the maximum length and configured thresholds. | Report **Class**. |

Length examples come from bounded listed or sampled values. **Distinct** in
the String analysis table counts values, not lengths. Scan also records string
characteristics such as case, non-ASCII content, line breaks and whitespace.

### Dates and times

The date detector separates unambiguous matches, ambiguous readings, invalid
date-shaped values and other present values. Report's **Date analysis** table
appears when it finds date evidence, even if the field's inferred type is not
`date`.

| Measure | Definition | Availability |
| --- | --- | --- |
| Valid, ambiguous, invalid, other | Counts and percentages of eligible present values by outcome. | Report **Date analysis** and detector coverage in Scan. |
| Formats | Counts for each recognized format, including numeric orders, date-times and times. | Scan detector and Report **Formats**. |
| Ambiguity evidence | Unambiguous values per DMY and MDY order; evidence is shown but not applied to ambiguous values. | Scan detector details and Report date profile. |
| Temporal range | Minimum and maximum per kind: `date`, naive date-time, aware date-time or `time`. Aware and naive values are not compared together. | Scan `temporal` and the standalone Report column page. |
| Years | Count per year when applicable to a temporal kind. | Scan `temporal` and the standalone Report column page. |

Only `scan.detectors.date.ambiguous_order` can explicitly resolve a supported
ambiguous day/month order. Ambiguous values do not contribute to the temporal
minimum and maximum.

### Boolean values and other meanings

Scan `booleans` counts native and recognized technical true/false values
separately as `true` and `false`; the standalone Report column page displays
those counts. The configurable boolean detector can additionally recognize
word pairs such as `yes/no` and `oui/non`; its matched counts and formats are
detector evidence, not the same as the technical boolean counts.

For `email`, `phone`, `postal_code`, `url`, `currency`, `percentage`,
`quantity`, `uuid`, `ip_address`, `enumeration` and configured patterns, the
shared measures are detector coverage, format counts and bounded examples.
Some detectors add details such as domains, hosts, units or UUID versions.
Those details are in [Recognized patterns](patterns.md) and the
[Scan detector result](../../scan/format.md#detectors); they do not imply
external verification.

### Limits and exposure

Scan wraps measures with a `status`: `complete`, `limited`, `not_applicable`,
`disabled` or `failed`. A limited measure is never estimated; a lower bound,
when present, is only a proven minimum. Sensitive fields can have numeric or
temporal measures disabled under masking or hiding, while counts remain
available. See [measure envelopes](../../scan/format.md#measure-envelopes)
and [exposure settings](../configuration.md#sensitive-values-and-sampling).
