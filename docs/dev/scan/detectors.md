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
- currency amounts and percentages, extended to quantities with a unit;
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

### Amounts (shared by `currency`, `percentage` and `quantity`)

The number part of an amount, a percentage or a quantity is read by the rules of
`number`, with the detector's own `conventions` and `ambiguous_convention`
(same defaults and validation as `detectors.number`, set independently), with
three restrictions: the sign is written outside the number part (below), no
exponent is accepted, and the number part is *amount-shaped*: it starts with
an ASCII digit, or `.` followed by a digit, ends with a digit or `.`, and
holds only digits, `.`, `,`, U+0020, U+00A0 and U+202F. An amount-shaped part
that `number` does not read (`12.5.0`, `1,2345.00`, `01.50`) makes the value
`invalid`, except a part made of digits only (`01`, `0012`): it carries no
number syntax, so it is `not_matched`, as the digits-only rule of `phone`,
and codes such as `01A` are never reported as invalid. A part that is not
amount-shaped (`.com`, `$.`) makes the value `not_matched`. A part that `number` finds
ambiguous (`1,234`) makes the value `ambiguous` with the candidates of
`number` (`#,##0` and `0,0`), unless `ambiguous_convention` resolves it.
Inherited from `number`: `1.234` is 1.234 by the strict rule, never
ambiguous (lot 3a note for gate 3).

The format is the format of the number part with the marker (currency symbol
or code, `%`, or the placeholder `[unit]` for quantities) and the space
between them as written, without the sign: `$#,##0.0`, `# ##0,0 €`,
`USD 0.0`, `0.0%`, `0,0 %`, `# ##0 [unit]`.

### `currency` (family `monetary`, version 1)

Amounts written with a currency marker. A number without marker is
`not_matched`: it is a `number`, not evidence of money.

- Accepts: strings; no input cap and no shapes: a value whose first character
  is not a sign, `(`, a currency symbol or an ASCII uppercase letter, and
  whose last character is not `)`, a currency symbol or an ASCII uppercase
  letter, is rejected first. The rejection is exact, so it is `not_matched`.
- Markers: the symbols `$`, `€`, `£`, `¥`, `CA$`, `C$`, `US$`, and the ISO
  4217 alphabetic codes of current currencies (list one on 2026-01-01, plus
  `ANG`, `BGN`, `HRK`, `SLL` and `ZWL`, replaced since 2023 but still found in
  data), in uppercase. Funds, precious metals, `XXX` and `XTS` are not
  markers. Three uppercase letters that are not such a code (`ABC 123`, an
  identifier) are `not_matched`.
- Formats: the marker before the number part (`$12.50`, `USD 12.50`) or after
  it (`12,50 $`, `1 234,56 €`, `12.50EUR`), with at most one space (U+0020,
  U+00A0 or U+202F) between them; format as in Amounts (`$0.0`, `0,0 $`,
  `# ##0,0 €`, `0.0EUR`). A negative amount has a `-` before the value
  (`-$12.50`, `-12,50 €`) or before the number part (`$-12.50`), or the whole
  value between parentheses without a sign (`($1,234.56)`, accounting); `+`
  is accepted where `-` is. One sign at most.
- Normalization: the analytical value (so a no-break space before `€` is
  already U+0020 when `collapse_whitespace` is enabled). Codes do not ignore
  case: `usd 12` is `not_matched`.
- Validation: a value with a marker at one end and an amount-shaped number
  part is a candidate; other values are `not_matched`, including values with
  two markers (`$12 USD`, `12 $ CA`). A candidate is `invalid` with reason
  `invalid_amount` when `number` does not read the number part. Ambiguity as
  in Amounts.
- Details: the `ambiguity` block of design 12.6 (evidence `comma` and `dot`
  when both conventions are enabled), and `currencies`, the count of matched
  and ambiguous values per marker as written, ordered by marker, such as
  `{"$": 10, "EUR": 2}`. Markers come from a fixed list: they carry no value
  of the field.
- Settings: `conventions` (default `["dot", "comma"]`),
  `ambiguous_convention` (`null`).
- Overlaps: `number` never matches (marker); `percentage`, `quantity`,
  `date`, `phone`, `postal_code`, `email` and `url` never match;
  `enumeration` and patterns may. The field's `numeric` block does not include currency amounts (design
  9.4): lot 5a decides whether the report needs them.
- Sensitive: no. An amount is not an identifier.
- Test values: `$12.50`, `$1,234.56`, `$.99`, `-$12.50`, `$-12.50`,
  `($1,234.56)`, `12,50 $`, `1 234,56 €`, `12€`, `£0.99`, `¥1000`,
  `CA$ 20`, `US$20`, `USD 12.50`, `12.50 EUR`; ambiguous `$1,234`,
  `1,234 €`; invalid `$12.5.0`, `$1,2345.00`, `€01.50`; not matched
  `12.50`, `$`, `$.`, `€012`, `USD`, `$abc`, `ABC 123`, `usd 12`, `$12 USD`, `12 $ CA`,
  `$1e3`, `-$-12`, `(-$12)`, `12%`, `CLI-00000281`.

### `percentage` (family `ratio`, version 1)

- Accepts: strings; no input cap and no shapes: a value whose last character
  is not `%` is rejected first. The rejection is exact, so it is
  `not_matched`.
- Formats: an optional sign (`-`, `+`), the number part, at most one space
  (U+0020, U+00A0 or U+202F), then `%`; format as in Amounts (`0%`, `0.0%`,
  `0,0 %`, `# ##0 %`).
- Normalization: the analytical value.
- Validation: a value ending with `%` whose remainder, without the space and
  the sign, is amount-shaped is a candidate; other values are `not_matched`.
  A candidate is `invalid` with reason `invalid_number` when `number` does
  not read the number part. Ambiguity as in Amounts. Values outside 0 to 100
  are percentages: a range is a judgment for consumers. The parsed value is
  the number as written (12 for `12%`).
- Details: the `ambiguity` block of design 12.6.
- Settings: `conventions` (default `["dot", "comma"]`),
  `ambiguous_convention` (`null`).
- Overlaps: `number` never matches (`%`); `currency`, `quantity`, `date`,
  `phone`, `postal_code`, `email` and `url` never match; `enumeration` and
  patterns may.
- Sensitive: no.
- Test values: `12%`, `12 %`, `12.5%`, `12,5 %`, `-3.5%`, `+2%`, `0%`,
  `150%`, `.5%`; ambiguous `1,234%`; invalid `12.5.0%`, `1,2,3 %`;
  not matched `05%`, `.%`, `12`, `%`, `12 %%`, `%12`, `12 pct`, `abc%`, `50% off`,
  `12% ` (with `trim` disabled).

### `quantity` (family `measurement`, version 1)

A number followed by a unit, whatever the unit: `10m`, `10 Go`,
`1 024 Mo`, `12,5 kg`, `90 km/h`, `20 °C`, `3 m²`. The detector checks the
syntax of a quantity; it does not know units, so it does not convert them or
check that they exist (EF32).

- Accepts: strings; no input cap and no shapes: a value whose first character
  is not a sign, `.` or an ASCII digit, or whose last character is not a
  letter (`str.isalpha`), `°`, `²` or `³`, is rejected first. The rejection
  is exact, so it is `not_matched`.
- Formats: an optional sign (`-`, `+`), the number part, at most one space
  (U+0020, U+00A0 or U+202F), then the unit; format as in Amounts with the
  placeholder `[unit]` (`0[unit]`, `0 [unit]`, `# ##0 [unit]`,
  `0,0 [unit]`), so formats stay bounded whatever the units. Units are listed
  in `details`.
- Unit: 1 to 12 characters, starting with a letter or `°`, made of letters
  (`str.isalpha`, any script: `µ`, `Ω` included), `°`, `²`, `³`, `/` and
  `·`, not ending with `/` or `·` (`km/h`, `kWh`, `mg/L`, `°C`, `m²`,
  `kg·m`). One token: `10 fl oz` and `3 rue des Lilas` are `not_matched`.
  Not units, so the value is `not_matched`:
  - currency markers of `currency` (`12 USD`, `12 €`), which belong to that
    detector;
  - ordinal suffixes, ignoring case: `er`, `re`, `e`, `ème`, `eme`, `nd`,
    `nde`, `st`, `rd`, `th` (`1er`, `2nd`, `21st`, `3e`).
- Normalization: the analytical value. Units keep their case: `Mo`
  (megaoctet) and `mo` (month) are different units.
- Validation: a value made of an amount-shaped number part, the optional
  space and a unit is a candidate; other values are `not_matched`. A
  candidate is `invalid` with reason `invalid_number` when `number` does not
  read the number part (`1,2,3 kg`, `01.5 m`); a number part of digits only
  is `not_matched` instead (`01 m`, `01A`). Ambiguity as in Amounts
  (`1,234 km`).
- Details: the `ambiguity` block of design 12.6, and `units`, the counted
  names block (above) of matched and ambiguous values' units as written (no
  lowercasing). Units are text of the field, so they go through the exposure
  gate.
- Settings: `conventions` (default `["dot", "comma"]`),
  `ambiguous_convention` (`null`), `max_tracked_units` (10,000, at most
  1,000,000), `max_listed_units` (20, at most 10,000).
- Overlaps: `number`, `currency` and `percentage` never match (unit, markers
  excluded, `%` is not a unit character); `date` never matches a single
  quantity token but `26 sept` is a quantity, not a date (no year);
  `postal_code` never matches (`H2X 1Y4` starts with a letter, `90210`
  ends with a digit); `email`, `url` and `phone` never match; `enumeration`
  and patterns may. A column of short counted words (`3 pommes`, `12 ans`)
  matches: they are quantities, as are codes such as `12B` or `2A`
  (apartments, Corsican departments) whose letters syntax cannot tell from
  a unit.
- Sensitive: no.
- Test values: `10m`, `10 m`, `10Go`, `10 Go`, `1 024 Mo`, `1,5 To`,
  `12.5 kg`, `-3 °C`, `20°C`, `90 km/h`, `3 m²`, `220 V`, `5 kWh`, `2 µs`,
  `12 ans`, `12B`; ambiguous `1,234 km`; invalid `1,2,3 kg`, `01.5 m`,
  `12.5.0 Go`; not matched `01 m`, `01A`, `.com`, `.NET`, `10`, `m`, `10 fl oz`, `3 rue des Lilas`, `12 USD`, `12 €`,
  `12%`, `1er`, `21st`, `10 km/`, `1e3m`, `10m2`, `H2X 1Y4`, `a 10 m`, a
  13-letter unit.

### `uuid` (family `identifier`, version 1)

Universally unique identifiers (RFC 9562, formerly RFC 4122), also called
GUIDs: 128 bits written as 32 hexadecimal digits.

- Accepts: strings; no input cap and no shapes: a value whose length is not
  36, 38 or 45 characters (the lengths of the accepted forms) is rejected
  first. The rejection is exact, so it is `not_matched`, not `not_tested`.
- Formats: 32 hexadecimal digits in groups of 8, 4, 4, 4 and 12 separated by
  `-`, as `hyphenated` (`123e4567-e89b-12d3-a456-426614174000`), between
  braces as `braced` (`{123e4567-e89b-12d3-a456-426614174000}`), or after
  the prefix `urn:uuid:`, ignoring its case, as `urn`. The format gets the
  suffix `_upper` when the hexadecimal letters are uppercase and `_mixed`
  when both cases appear (`hyphenated_upper`); digits alone count as
  lowercase. Not accepted in version 1, so `not_matched`: 32 bare digits
  (`123e4567e89b12d3a456426614174000`), which syntax cannot tell from an MD5
  hash, other groupings, other separators, a single brace.
- Normalization: the analytical value; hexadecimal digits ignore case.
- Validation: a value with the layout of a form above, its groups made of
  ASCII letters and digits, is a candidate; other values are `not_matched`.
  A candidate with a letter beyond `f` is `invalid` with reason
  `invalid_hex_digit`. The version and variant are not validated: NCS,
  Microsoft and reserved variants are UUIDs too, and generated test values
  (`12345678-1234-1234-1234-123456789012`) must not fail; `details` counts
  them. No value is ambiguous.
- Details: `versions`, the matched count per version, keys with a non-zero
  count only, ordered by key: `"1"` to `"8"` for the RFC 9562 variant (the
  first digit of the fourth group is `8`, `9`, `a` or `b`), `"nil"` (all
  zeros), `"max"` (all `f`), and `"other"` for other variants and undefined
  versions. Such as `{"4": 10, "other": 1}`. Keys carry no value.
- Settings: none besides `enabled`.
- Overlaps: none of `number`, `date`, `phone`, `postal_code`, `currency`,
  `percentage`, `quantity`, `email`, `url` and `ip_address` matches (length,
  hyphens, digits and letters mixed in groups); `enumeration` and patterns
  may.
- Sensitive: no. A UUID identifies a record, as a customer number does; it
  does not identify a person without other data. A sensitive pattern can
  flag identifiers where needed.
- Test values: `123e4567-e89b-12d3-a456-426614174000`,
  `123E4567-E89B-12D3-A456-426614174000`, `123E4567-e89b-12d3-a456-426614174000`,
  `{123e4567-e89b-12d3-a456-426614174000}`,
  `urn:uuid:123e4567-e89b-12d3-a456-426614174000`,
  `URN:UUID:123e4567-e89b-12d3-a456-426614174000`,
  `00000000-0000-0000-0000-000000000000` (nil),
  `ffffffff-ffff-ffff-ffff-ffffffffffff` (max),
  `12345678-1234-1234-1234-123456789012` (other); invalid
  `123e4567-e89b-12d3-a456-42661417400g`; not matched
  `123e4567e89b12d3a456426614174000`, `123e4567-e89b-12d3-a456-4266141740`,
  `123e4567_e89b_12d3_a456_426614174000`, `{123e4567-e89b-12d3-a456-426614174000`,
  `123e4567-e89b-12d3-a456-426614174000 `, `12345678-1234-1234-1234-12345678901é`,
  `CTR-1000000281`, `2026-09-26`.

### `ip_address` (family `network`, version 1)

IPv4 addresses in dotted-decimal notation and IPv6 addresses in the text
forms of RFC 4291, as written in logs and network inventories.

- Accepts: strings; no input cap and no shapes: a value shorter than 2 or
  longer than 45 characters (the shortest and longest accepted forms, `::`
  and `ffff:ffff:ffff:ffff:ffff:ffff:255.255.255.255`), or whose first or
  last character is neither an ASCII hexadecimal digit nor `:`, is rejected
  first. The rejection is exact, so it is `not_matched`.
- Formats: `ipv4` (`192.0.2.1`); `ipv6` for eight groups
  (`2001:db8:0:0:0:0:0:1`), `ipv6_compressed` for a value with `::`
  (`2001:db8::1`, `::1`, `::`), and `ipv6_ipv4` when the last 32 bits are
  written as an IPv4 address, compressed or not (`::ffff:192.0.2.1`). Not
  accepted in version 1, so `not_matched`: prefix lengths (`192.0.2.0/24`),
  ports (`192.0.2.1:80`), brackets (`[2001:db8::1]`), zone indices
  (`fe80::1%eth0`), and IPv4 shorthands (`127.1`, hexadecimal or octal
  groups). `url` covers addresses inside URLs.
- Normalization: the analytical value; hexadecimal digits ignore case.
- Validation: a value that is a candidate of one version is checked; other
  values are `not_matched`. Reasons are those of the first failed check, in
  the order below, groups from left to right.
  - IPv4 candidate: four groups of 1 to 3 ASCII digits separated by `.`.
    `invalid_leading_zero` when a group of two or three digits starts with
    `0` (`192.168.01.1`, read as octal by some tools); `invalid_octet` when
    a group is above 255.
  - IPv6 candidate: made only of ASCII hexadecimal digits, `:` and `.`, with
    at least two `:`, and either containing `::` or having at least eight
    groups separated by `:`, a last group with `.` counting as two. So times
    (`22:00:00`) and MAC addresses (`00:1A:2B:3C:4D:5E`) are `not_matched`.
    `invalid_compression` when `::` appears twice or `:::` appears;
    `invalid_group` when a group is empty (a single leading or trailing
    `:`), has more than four digits, or holds `.` without being the last
    group of four decimal groups; `invalid_group_count` when there are more
    than eight groups, or eight or more with `::`; then the embedded IPv4
    address is checked as above.

  No value is ambiguous: the two versions never share a candidate.
- Details: `versions`, the matched count per enabled version, such as
  `{"ipv4": 10, "ipv6": 2}`, ordered by version. Counts carry no value.
- Settings: `versions` (default `["ipv4", "ipv6"]`, unique, at least one).
- Overlaps: `number` matches an IPv4 address whose last three groups have
  three digits (`192.168.100.200`), read as 192168100200 by the `comma`
  convention, so such columns list both interpretations and have no primary;
  other addresses (`192.168.1.1`) are not numbers. Version numbers of four
  numeric parts (`1.0.0.12`) are IPv4 syntax and EUI-64 identifiers written
  in eight colon groups are IPv6 syntax: syntax cannot tell them apart.
  `date`, `phone`, `postal_code`, `currency`, `percentage`, `quantity`,
  `email`, `url` and `uuid` never match; `enumeration` and patterns may.
- Sensitive: yes. An IP address can identify a subscriber or a device and is
  personal data in several jurisdictions, as email addresses and phone
  numbers are: its fields are masked by default (`999.999.9.9`), and a
  column where `number` also matches has its `numeric` block disabled under
  `mask` and `hide`.
- Test values: `192.0.2.1`, `0.0.0.0`, `255.255.255.255`, `10.0.0.1`,
  `2001:db8:0:0:0:0:0:1`, `2001:DB8::1`, `::1`, `::`, `fe80::`,
  `1:2:3:4:5:6:7::`, `::ffff:192.0.2.1`, `64:ff9b::192.0.2.1`,
  `0:0:0:0:0:ffff:192.0.2.1`; invalid `192.168.01.1`, `256.1.1.1`,
  `2001:db8::1::2`, `2001:::1`, `2001:db8:0:0:0:0:0:12345`,
  `:1:2:3:4:5:6:7`, `1:2:3:4:5:6:7:8:9`, `1:2:3:4::5:6:7:8`,
  `::ffff:192.168.1.300`, `::ffff:1.2.3`, `1.2.3.4::`; not matched
  `1.2.3`, `1.2.3.4.5`, `1234.1.1.1`, `192.0.2.0/24`, `192.0.2.1:80`,
  `[2001:db8::1]`, `fe80::1%eth0`, `22:00:00`, `00:1A:2B:3C:4D:5E`,
  `2001:db8:0:0:0:0:1`, `2001:dg8::1`, `127.1`, `514.555.0100`, `12:30`.
