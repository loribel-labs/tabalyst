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

Catalogue detectors are costlier than the built-ins: they should declare a
`max_input_length`, and reject most values with a cheap exact check, such as
a required character or first character, or declare `shapes` (design 12.5)
when no such check exists. Measured in the email and URL session: shapes on
both detectors made the 100,000-row benchmark file about 30% slower, a
required character check about 8%, because the signature is computed for
nearly every value. A detector whose values
identify people (email addresses, phone numbers) is `sensitive`, so its
fields are masked by default; any value it carries in `details` goes through
the exposure gate.

### Domain names (shared by `email` and `url`)

A domain name is one or more labels separated by dots. A label has 1 to 63
characters among letters of any script (`str.isalpha`, so internationalized
names such as `exemple.québec` are accepted as written), ASCII digits and
`-`, and neither starts nor ends with `-`. The name has at most 253
characters, no empty label (so no leading, trailing or doubled dot), and its
last label is not made of digits only. Punycode labels (`xn--`) are ordinary
labels; they are not decoded.

### Counted names (shared by `email` and `url`)

`email` counts domains and `url` counts hosts, lowercased with
`str.lower` (not `casefold`, which would merge `straße` and `strasse`), with the same
block. Only `matched` values count.

```json
{"status": "complete", "value": {"distinct": 3, "listed": [{"value": "example.com", "count": 5}], "truncated": false}}
{"status": "limited", "reason": "max_tracked", "limit": 10000, "lower_bound": 10001}
```

- A name is tracked from its first occurrence, so tracked counts are exact.
  When a name beyond `max_tracked` distinct names arrives, the block is
  `limited` and has no value: the most frequent names are no longer proven.
- `listed` holds the `max_listed` most frequent names, ordered by count
  (descending), then name; `truncated` says the listing is shorter than
  `distinct`.
- The names go through the exposure gate (`gate.counts`): under `mask`,
  equal masks merge before ranking and `distinct` counts masks; under `hide`,
  `listed` is empty and `truncated` is `true` when a name was hidden. A
  `limited` block publishes `lower_bound` under `show` and `hide`, where
  `distinct` counts raw names, and omits it under `mask`, since distinct raw
  names do not prove distinct masks.

### `email` (family `contact`, version 1)

- Accepts: strings; input cap 254 characters (the longest address SMTP
  allows); no shapes: a value without `@` is rejected first, which is
  cheaper than a shape signature.
- Formats: none. Only a bare address (`addr-spec`) is recognized: quoted
  local parts, comments, display names (`Jane <jane@example.com>`), IP
  address literals (`jane@[192.0.2.1]`) and `mailto:` are not matched.
- Normalization: the analytical value. The domain ignores case in `details`;
  the local part is kept as written.
- Validation: a value is a candidate when it has exactly one `@`, a non-empty
  local part without `:`, `/`, `<` or `>`, and a domain with at least one dot and
  none of `/`, `?`, `#`, `:`, `<`, `>`, `[`, `]`. These characters mark URLs,
  display names and address literals; other values are `not_matched`. A
  space or an underscore does not, so a mistyped address such as
  `jane@gmail. com` or `jane doe@example.com` is `invalid`.
  A candidate is `invalid` with the reason of the first failed check, in
  this order:
  - `local_part_too_long`: more than 64 characters;
  - `invalid_local_part`: not a dot-atom, that is characters outside ASCII
    letters, digits and ``!#$%&'*+/=?^_`{|}~-`` separated by single dots,
    with no leading or trailing dot (non-ASCII local parts included);
  - `invalid_domain`: not a domain name (above).

  No value is ambiguous.
- Details: `domains`, the counted names block (above).
- Settings: `max_tracked_domains` (10,000, at most 1,000,000),
  `max_listed_domains` (20, at most 10,000).
- Overlaps: `url` never matches an address: a `www.` URL has no `@` in its
  authority, and a URL with `@` elsewhere has `:` or `/` before the `@`; `enumeration` and patterns
  may.
- Sensitive: yes, an address identifies a person.
- Test values: `jane@example.com`, `Jane.Doe+tag@Mail.Example.CO.UK`,
  `j@exemple.québec`, `o'brien@example.ie`; invalid `.jane@example.com`,
  `jane..doe@example.com`, `josé@example.com`, `jane@-example.com`,
  `jane@example.123`, `jane@gmail. com`, `jane doe@example.com`, a
  65-character local part; not matched `jane`,
  `jane@localhost`, `jane@@example.com`, `a@b@example.com`,
  `Jane <jane@example.com>`, `mailto:jane@example.com`,
  `https://jane@example.com`.

### `url` (family `web`, version 1)

- Accepts: strings; input cap 8,192 characters; no shapes: a value whose
  first character is not the first letter of a configured scheme or `w`,
  ignoring case, is rejected first.
- Formats: absolute URLs of a configured scheme, ignoring case, followed by
  `://`, with format the scheme in lowercase (`http`, `https`, `ftp`); URLs
  without scheme starting with `www.`, ignoring case, with format `www`.
- Normalization: the analytical value. The scheme and the host ignore case.
- Validation: a value is a candidate when it starts with `<scheme>://` of a
  configured scheme, or with `www.` followed by an authority without `@`;
  other values are `not_matched`. The authority runs up to the first `/`, `?`
  or `#`: optional user information ending with `@` (scheme form only),
  host, optional `:port`. A candidate is `invalid` with the reason of the
  first failed check, in this order:
  - `invalid_character`: whitespace, a control character or an ASCII
    character outside RFC 3986 (`"`, `<`, `>`, `\`, `^`, `` ` ``, `{`, `|`,
    `}`) anywhere in the value. Other non-ASCII characters are accepted,
    as browsers display them (IRI);
  - `invalid_percent_encoding`: `%` not followed by two hexadecimal digits;
  - `invalid_host`: empty host, or a host that is neither a domain name
    (above; a single label such as `localhost` is accepted in the scheme
    form), nor an IPv4 address in dotted decimal, nor an IPv6 address between
    brackets (checked with `ipaddress`);
  - `invalid_port`: a port that is empty or not 1 to 5 ASCII digits up to
    65535.

  No value is ambiguous.
- Details: `hosts`, the counted names block (above), without user
  information or port; IPv6 hosts keep their brackets.
- Settings: `schemes` (default `["http", "https", "ftp"]`, unique lowercase
  ASCII letters), `www` (true), `max_tracked_hosts` (10,000, at most
  1,000,000), `max_listed_hosts` (20, at most 10,000).
- Overlaps: `email` (see above); `number` and `date` never match a candidate;
  `enumeration` and patterns may.
- Sensitive: no. A URL names a resource, not a person; query strings may
  still carry personal data or tokens, which a sensitive pattern can flag.
- Test values: `https://example.com`, `HTTP://Example.com:8080/a?b=c#d`,
  `ftp://files.example.com/x.csv`, `http://localhost:8000`,
  `http://192.0.2.1/`, `http://[2001:db8::1]/`, `https://user:pw@example.com`,
  `https://exemple.québec/été`, `www.example.com/path`; invalid
  `https://`, `https://exa mple.com`, `http://example.com:99999`,
  `http://example.com/%zz`, `http://-example.com`, `http://999.1.1.1`,
  `http://example.com/{id}`; not matched `example.com`, `mailto:x@y.z`,
  `file:///tmp/x`, `javascript:alert(1)`, `www.jane@example.com`, `wwwexample`.

### `phone` (family `contact`, version 1)

Phone numbers of the North American Numbering Plan (region `nanp`: Canada,
the United States and the other NANP countries, which syntax cannot tell
apart) and of France (region `fr`). Numbers of other countries are
`not_matched`: the detector covers its regions, not every phone number.

- Accepts: strings; no input cap and no shapes: a value shorter than 10 or
  longer than 22 characters (the shortest and longest accepted forms,
  `0612345678` and `0033 (0) 6 12 34 56 78`), or
  whose first character is not `+`, `(` or a digit, or whose last character
  is not a digit, or that does not have 10 to 14 ASCII digits once spaces,
  `.`, `-`, `(`, `)` and `+` are removed, is rejected first. The rejection is
  exact, so it is `not_matched`, not `not_tested`.
- Formats: the value with every digit of the number replaced by `9`, keeping
  the country code, the international prefix and the trunk prefix as written
  (`(999) 999-9999`, `+1-999-999-9999`, `1 999 999 9999`, `9999999999`,
  `09 99 99 99 99`, `+33 9 99 99 99 99`, `+33 (0)9 99 99 99 99`,
  `0033999999999`). Separators are U+0020, `-` and `.`; line breaks and other
  characters are not accepted.
  - `nanp`: an optional `+1` or trunk prefix `1`, optionally followed by one
    separator; a three-digit area code, either between parentheses followed by
    an optional space, or followed by an optional separator; a three-digit
    exchange code, an optional separator and four digits. Separators may
    differ (`(514) 555-0100`).
  - `fr`, national: `0` and nine digits, either bare or as five pairs with one
    separator used throughout (`06 12 34 56 78`, `06.12.34.56.78`).
  - `fr`, international: `+33` or `0033`, an optional separator, an optional
    `(0)` with an optional space, then nine digits, either bare or as one digit and four pairs with
    one separator used throughout (`+33 6 12 34 56 78`).
- Normalization: the analytical value (runs of whitespace are already one
  space).
- Validation: a value that has one of the forms above is a candidate; other
  values are `not_matched`. A candidate is `invalid` with the reason of the
  first failed check:
  - `invalid_area_code` (`nanp`): the area code starts with `0` or `1`;
  - `invalid_exchange_code` (`nanp`): the exchange code starts with `0` or
    `1`;
  - `invalid_trunk_prefix` (`fr`): the international form is followed by a
    national number with its trunk `0` outside parentheses
    (`+33 06 12 34 56 78`);
  - `invalid_leading_digit` (`fr`): the digit after the trunk `0` or the
    country code is `0`.

  A value made of digits only carries no phone syntax: it is `matched` when
  valid and `not_matched` otherwise, never `invalid`, so that columns of
  numeric identifiers are not reported as invalid phones. N11 service codes,
  unassigned area codes and extensions (`x123`) are not checked or accepted
  in version 1. The regions' forms never overlap, so no value is ambiguous.
- Details: `regions`, the matched count per enabled region, such as
  `{"fr": 2, "nanp": 10}`, ordered by region. Counts carry no value.
- Settings: `regions` (default `["nanp", "fr"]`, unique, at least one).
- Overlaps: `number` matches bare NANP numbers (`5145550100`,
  `15145550100`, `+15145550100`) as integers, so such columns list both
  interpretations and have no primary; French bare numbers start with `0`,
  which `number` rejects. `date` never matches (`2026-09-26` has 8 digits);
  `email` and `url` never match (first character); `enumeration` and patterns
  may.
- Sensitive: yes, a phone number identifies a person.
- Test values: `(514) 555-0100`, `514-555-0100`, `514.555.0100`,
  `+1 514 555 0100`, `+1-468-555-0110`, `1-800-555-0199`, `5145550100`,
  `06 12 34 56 78`, `01.23.45.67.89`, `0612345678`, `+33 6 12 34 56 78`,
  `+33 (0)6 12 34 56 78`, `+33612345678`, `0033 1 23 45 67 89`; invalid
  `123-456-7890` (area code), `514-055-0100` (exchange code),
  `+33 06 12 34 56 78` (trunk prefix), `00 12 34 56 78` (leading digit); not
  matched `1234567890`, `555-0100`, `+44 20 7946 0958`, `06 12 34 56 7`,
  `06-12 34-56-78`, `514-555-0100 x12`, `192.168.100.200`, `2026-09-26`.

### `postal_code` (family `address`, version 1)

Canadian postal codes (region `ca`) and United States ZIP codes (region
`us`). Codes of other countries are `not_matched`: the detector covers its
regions, not every postal code.

- Accepts: strings; no input cap and no shapes: a value whose length is not 5,
  6, 7 or 10 characters (the lengths of the accepted forms) is rejected
  first, then a value whose first character is neither an ASCII digit (`us`)
  nor an ASCII letter (`ca`) of an enabled region. The rejection is exact, so
  it is `not_matched`, not `not_tested`.
- Formats: the value with each uppercase letter as `A`, each lowercase letter
  as `a` and each digit as `9`, other characters kept.
  - `ca`: letter, digit, letter, an optional space, digit, letter, digit,
    ignoring case (`H2X 1Y4`, `h2x1y4`); formats `A9A 9A9`, `A9A9A9`,
    `a9a 9a9`. A hyphen or any other separator is not accepted.
  - `us`: five digits (ZIP, format `99999`), optionally followed by `-` and
    four digits (ZIP+4, format `99999-9999`). A space or no separator before
    the four digits is not accepted: nine bare digits carry no ZIP syntax.
- Normalization: the analytical value (so `H2X  1Y4` is `H2X 1Y4`); letters
  ignore case for validation.
- Validation: a value that has one of the forms above is a candidate; other
  values are `not_matched`. A `ca` candidate is `invalid` with the reason of
  the first failed check, as published by Canada Post:
  - `invalid_first_letter`: the first letter is not one of
    `ABCEGHJKLMNPRSTVXY` (it is `D`, `F`, `I`, `O`, `Q`, `U`, `W` or `Z`);
  - `invalid_letter`: the second or third letter is `D`, `F`, `I`, `O`, `Q`
    or `U`.

  `us` candidates are never `invalid`: any five digits are ZIP syntax, and
  unassigned codes such as `00000` are a real-world check (EF32). Truncated
  or partial values (`T3A 95`, `2134` for a ZIP code whose leading zero was
  lost) are `not_matched`. The regions' forms never overlap, so no value is
  ambiguous.
- Details: `regions`, the matched count per enabled region, such as
  `{"ca": 10, "us": 2}`, ordered by region. Counts carry no value.
- Settings: `regions` (default `["ca", "us"]`, unique, at least one).
- Overlaps: `number` matches every ZIP code without a leading zero (`90210`)
  as an integer, so a column of five-digit integers, identifiers included,
  lists both interpretations and has no primary (CA10); a ZIP code with a
  leading zero (`02134`) is not a number. ZIP+4 codes and Canadian codes are
  not numbers. `phone` never matches (at most 9 digits), nor do `date`,
  `email` and `url`; `enumeration` and patterns may.
- Sensitive: no. A postal code is a quasi-identifier, not an identifier: it
  designates an area shared by many households, and a sensitive ZIP code
  would mask every column of five-digit integers and disable its statistics.
  A sensitive pattern can flag postal codes where the context requires it.
- Test values: `H2X 1Y4`, `h2x1y4`, `K1A 0B1`, `90210`, `02134`,
  `12345-6789`; invalid `D2X 1Y4`, `W1A 1A1` (first letter), `H2O 1Y4`,
  `H2X 1U4` (letter); not matched `H2X-1Y4`, `H2X 1Y`, `T3A 95`, `2134`,
  `123456`, `123456789`, `12345 6789`, `12345-678` (Brazilian CEP),
  `SW1A 1AA`, `75008 Paris`, `É2X 1Y4`, `٩٠٢١٠`.
