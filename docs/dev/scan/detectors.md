# Tabalyst Scan detectors

One short specification per detector (design section 12.9, O14). A detector
gets its entry here before it is implemented; the contract it follows is
design section 12. Detectors check syntax, never real-world existence (EF32).

## Entry template

```text
### `<id>` (family `<family>`, version <n>)

- Accepts: native types; input cap; shapes, if any.
- Formats: accepted forms and the `format` names they produce.
- Normalization: the analytical value (design 10) plus anything the detector
  applies itself, such as ignoring case.
- Validation: what makes a value `invalid` rather than `not_matched`, with
  reasons; `ambiguous` values and their candidates.
- Details: the `details` block; value-bearing members go through the
  exposure gate.
- Settings: `detectors.<id>` parameters and defaults.
- Overlaps: other detectors that match the same values.
- Sensitive: yes or no, and why.
- Test values: positive, negative, variant and overlap examples.
```

Every built-in accepts strings only, since native JSON values are already
typed; accepted digits are ASCII digits.

## Built-in detectors (lot 3a)

### `number` (family `number`, version 1)

- Accepts: strings; no input cap, no shapes.
- Formats: the strict rule applies first. A strict integer (`0`, `-12`)
  matches under any convention with format `0`. Strict decimals and exponents
  (`1.5`, `.5`, `1.`, `1e3`) match with formats `0.0` and `0E0` when the
  `dot` convention is enabled. Values the strict rule rejects are read under
  each enabled convention, with digits on both sides of the decimal
  separator, no leading zeros and thousands grouped by three with one
  separator used throughout:

  | Convention | Decimal | Thousands |
  | --- | --- | --- |
  | `dot` | `.` | `,`, U+0020, U+00A0, U+202F |
  | `comma` | `,` | `.`, U+0020, U+00A0, U+202F |

  Formats follow spreadsheet notation with the separators seen: `#,##0`,
  `#,##0.0`, `0,0`, `#.##0,0`, `# ##0`.
- Normalization: the analytical value.
- Validation: two readings with the same value (`1 234`) match; different
  values (`1,234`) are ambiguous. The strict rule decides `1.234` (1.234, not
  1234) so that lot 2a results are unchanged; it is not ambiguity evidence.
  No value is `invalid`.
- Details: the `ambiguity` block of design 12.6, with `evidence` for `comma`
  and `dot` when both are enabled. A decimal point or comma read by one
  convention only is evidence for it.
- Settings: `conventions` (default `["dot", "comma"]`), `ambiguous_convention`
  (`null`).
- Overlaps: `date` never matches a number; `enumeration` and catalogue codes
  (ZIP codes) may.
- Sensitive: no.
- Test values: `12`, `-1.5`, `1e3`, `12,5`, `1.234,5`, `1 234`; ambiguous
  `1,234`; not matched `01`, `1,23,4`, `NaN`.

### `date` (family `temporal`, version 1)

- Accepts: strings; no input cap, no shapes.
- Formats:
  - numeric dates of the current engine: a four-digit year first (`YMD`) or
    last (`MDY`, `DMY`), one- or two-digit month and day, one configured
    separator used twice; formats such as `YYYY-MM-DD`, `D/M/YYYY`;
  - ISO 8601 date-times: `YYYY-MM-DD`, `T` or a space, `HH:MM`, optional
    seconds and fraction of one to six digits, optional `Z` or offset (`+HH`,
    `+HHMM`, `+HH:MM`); formats such as `YYYY-MM-DDTHH:MM:SS.fff±HH:MM`;
  - times: `H:MM` or `HH:MM`, optional seconds and fraction;
  - dates with month names, ignoring case: day first in English and French
    (`26 September 2026`, `1er janvier 2026`, `26 sept. 2026`), month first in
    English (`September 26, 2026`); full names format as `MMMM`,
    abbreviations as `MMM` or `MMM.`; French names are also accepted without
    accents.
- Normalization: the analytical value; month names ignore case.
- Validation: `invalid` values have an accepted form but fail validation,
  with reasons `invalid_calendar_date`, `invalid_time`, `invalid_offset`,
  `invalid_component_width`, `mixed_separators` and `unsupported_order`, as in
  the current engine. `01/02/2026` is ambiguous when both `DMY` and `MDY` are
  enabled.
- Details: the `ambiguity` block of design 12.6, with `evidence` for `DMY` and
  `MDY`. The detector also produces the field's `temporal` block (design 9.6).
- Settings: `orders`, `separators`, `ambiguous_order` (as the current engine)
  and `month_languages` (default `["en", "fr"]`). ISO date-times do not
  depend on `orders` and `separators`.
- Overlaps: none with `number`; `enumeration` may.
- Sensitive: no. Birth dates are sensitive by context, not by syntax.
- Test values: `2026-09-26`, `26/09/2026`, `2026-09-26T22:00:00Z`, `22:00`,
  `26 sept. 2026`; invalid `2026-02-30`, `25:00`; ambiguous `01/02/2026`.

### `boolean` (family `boolean`, version 1)

- Accepts: strings.
- Formats: the pair of the matched word (`yes/no`).
- Normalization: the analytical value, ignoring case.
- Validation: none; a word of a configured pair matches.
- Details: `{"true": n, "false": m}`.
- Settings: `pairs`, default `true/false`, `yes/no`, `y/n`, `oui/non`,
  `vrai/faux`; words are unique ignoring case.
- Overlaps: `enumeration`. Only `true` and `false` count in the technical type
  family `boolean` (design 9.7).
- Sensitive: no.
- Test values: `Yes`, `n`, `VRAI`; not matched `1`, `ok`.

### `enumeration` (family `categorical`, version 1, field-level)

- Accepts: strings.
- Formats: none.
- Normalization: the analytical value, ignoring case when `case_sensitive` is
  false.
- Validation: every value matches when the field has at least
  `minimum_values` eligible values and at most `maximum_distinct` distinct
  analytical values; otherwise none matches. It counts eligible values rather
  than rows.
- Details: `distinct`, `complete` with the count or `limited` with reason
  `maximum_distinct` and lower bound `maximum_distinct + 1`. It keeps at most
  `maximum_distinct + 1` values, so it stays exact when frequency tables are
  released.
- Settings: `minimum_values` (500), `maximum_distinct` (49),
  `case_sensitive` (true).
- Overlaps: any value detector; an integer code column may be both a number
  and an enumeration (CA10).
- Sensitive: no.
- Test values: 500 values among `A`, `B`, `C` match; 499 values, or 50
  distinct values, do not.

## Declarative patterns (lot 3b)

### `pattern:<id>` (family `pattern`, version 1)

- Accepts: the native types of the entry's `accepts` (default `["string"]`);
  other types are canonical text (design 9.1). Values longer than
  `max_input_length` (default 256, at most 10,000) are `not_tested`. No
  shapes.
- Formats: none.
- Normalization: the analytical value; the expression decides everything
  else, such as case with `(?i)`.
- Validation: `re.fullmatch` of the compiled expression; no `invalid` or
  `ambiguous` values.
- Details: none.
- Settings: the `patterns` entry itself: `id` (1 to 64 characters among
  letters, digits, `_` and `-`), `regex` (at most 1,000 characters, compiled
  at configuration validation), `description`, `accepts`, `sensitive`,
  `max_input_length`. At most 200 patterns, with unique ids. Pattern detectors
  follow the registry, in configuration order; an id that a registered
  detector already uses is a configuration error.
- Overlaps: any detector.
- Sensitive: when the entry says so.
- Test values: `C-\d{4}` matches `C-0001`, not `X-1` nor `C-00012`.
- Patterns are trusted configuration: Python `re` has no timeout, so a
  hostile expression can backtrack catastrophically.

## Priority 1 catalogue (lot 3b)

Each family writes its entries here before implementing them, in its own
session (plan.md, lot 3b):

- email and URL;
- phone numbers (CA, US, FR);
- postal codes (CA) and ZIP codes (US);
- currency amounts and percentages;
- UUID and IP addresses.

Catalogue detectors are costlier than the built-ins: they should declare
`shapes` (design 12.5) and a `max_input_length`. A detector whose values
identify people (email addresses, phone numbers) is `sensitive`, so its
fields are masked by default; any value it carries in `details` goes through
the exposure gate.
