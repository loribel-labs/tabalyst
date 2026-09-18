# Configuration

Tabalyst reads strict JSON configuration files. JSON does not allow comments;
this page is the descriptive reference for supported settings. A `tabalyst.json`
file in the current working directory is loaded automatically. Files passed to
`--config` are applied afterward in order: later settings replace earlier ones,
while CLI options remain the final override.

## CSV and preview

```json
{
  "csv": {
    "encoding": "utf-8-sig",
    "delimiter": ","
  },
  "missing_values": [""],
  "preview_rows": 10
}
```

- `csv.encoding`: source-file encoding. The default accepts UTF-8 with or without
  a BOM; `cp1252` is useful for some Windows-produced files.
- `csv.delimiter`: single-character separator, a comma by default.
- `missing_values`: strings treated as missing after surrounding whitespace is
  stripped. Comparisons remain case-sensitive.
- `preview_rows`: number of raw rows embedded in the report, from 0 to 100. It
  never limits analysis of the complete CSV.

## Value normalization

```json
{
  "normalization": {
    "trim": true,
    "collapse_internal_whitespace": true
  }
}
```

- `trim`: removes leading and trailing Unicode whitespace before analysis.
- `collapse_internal_whitespace`: replaces each internal run of horizontal
  whitespace, including tabs and non-breaking spaces, with one ordinary space.
  Line breaks are preserved.

Normalization affects type inference, distinct values, occurrences, examples and
`enum` detection. Raw CSV values remain available in the data preview, and exact
duplicate rows still compare raw values. Each column records the number and
percentage of cells changed by each operation; the dataset summary also records
both global counts. A cell changed by both operations contributes to both counts,
but never more than once to the same operation.

## Date detection

```json
{
  "date_detection": {
    "enabled": true,
    "orders": ["YMD", "MDY", "DMY"],
    "separators": ["-", "/", "."],
    "ambiguous_order": null
  }
}
```

- `enabled`: turns strict date profiling on or off.
- `orders`: accepted component orders. Years must use four digits; months and days
  may use one or two digits.
- `separators`: accepted single-character separators. Each value must use the same
  separator between both component pairs.
- `ambiguous_order`: optionally resolves values such as `02/03/2025` as `MDY` or
  `DMY`. With `null`, Tabalyst resolves them only when the same column contains
  unambiguous evidence for one order and none for the other.

Every recognized structure is validated against the calendar, including leap
years. Profiles count valid, ambiguous, invalid and non-date values separately,
then group valid occurrences by order and separator. `YYYY-MM-DD` is specifically
marked as ISO; other separators using `YMD` remain valid but are not labeled ISO.
Arbitrary text is not treated as a date error.

## Examples and value profiles

```json
{
  "value_examples": {
    "full_distribution_max_distinct": 50,
    "candidate_sample_size": 100,
    "short_text_max_length": 20,
    "short_text_percentile": 0.95,
    "short_text_result_size": 20,
    "long_text_result_size": 20,
    "long_text_truncate_at": 30,
    "truncation_suffix": "...",
    "inline_display_size": 3,
    "random_seed": 42
  }
}
```

- `full_distribution_max_distinct`: through this limit, every non-missing
  distinct value and its occurrence count are retained in JSON. At `50`, the
  distribution is still complete; at `51`, Tabalyst samples values.
- `candidate_sample_size`: maximum number of distinct values reproducibly sampled
  before final selection.
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
- `random_seed`: sampling seed, which makes JSON and reports reproducible for the
  same CSV and configuration.

The `Examples` cell shows `+N` for a complete distribution. For a sampled profile,
it shows `++`; the tooltip then shows, for example, `20 / 2,992`, meaning retained
values / actual distinct values. Tooltip values are sorted by descending occurrence
count.

## Enum candidates

```json
{
  "enum_detection": {
    "enabled": true,
    "minimum_row_count": 500,
    "maximum_distinct_values": 49,
    "eligible_types": ["text"],
    "case_sensitive": true
  }
}
```

- `enabled`: turns on optional semantic classification.
- `minimum_row_count`: minimum dataset size before an `enum` candidate is proposed.
- `maximum_distinct_values`: maximum observed non-missing value count.
- `eligible_types`: physical types that can receive the marker; the default limits
  detection to `text` columns.
- `case_sensitive`: decides whether `Open` and `open` are separate values.

`enum` is a semantic hint: its physical type remains `text`. The report then shows
both badges as `text · enum`.
