---
title: Recognized patterns
description: Catalog every built-in Tabalyst detector, its accepted forms, configured patterns and evidence states.
---

**Tabalyst Scan** applies detectors to eligible field values and records
matched, ambiguous, invalid, unmatched and untested counts. **Tabalyst
Report** shows detectors with evidence in **Detectors and formats**. A pattern
match means the value fits the detector's rule; it does not prove that an
address, phone number or identifier exists in an external system. The
[Types page](types.md) explains how one detector can become a semantic type.

## Built-in detectors

The table lists every built-in detector ID. Its examples show representative
forms, not the complete grammar. Defaults can change through
[`scan.detectors`](../configuration.md#detectors). A field can have evidence
from several detectors at once.

| Detector ID | What is recognized | Representative forms and limits |
| --- | --- | --- |
| `number` | Integers, decimals and scientific notation under configured dot/comma conventions. | `42`, `12.5`, `12,5`, `1e3`; `1,234` may be ambiguous until a convention is set. |
| `date` | Numeric dates, ISO date-times, times and English/French month-name dates. | `2026-10-06`, `02/03/2026`, `2026-10-06T12:30Z`, `13:45`, `26 September 2026`. Orders and separators are configurable; impossible dates are invalid, and ambiguous DMY/MDY values stay unresolved by default. |
| `boolean` | Configured pairs of textual truth values. | Defaults: `true/false`, `yes/no`, `y/n`, `oui/non`, `vrai/faux`; native JSON booleans are already technical values. |
| `enumeration` | A low-cardinality field, considered as a whole. | Defaults: at least 500 eligible values and at most 49 distinct analytical values; case-sensitive by default. |
| `email` | Bare `local@domain` with a dot-atom local part and valid domain syntax. | `name@example.com`; display names and addresses embedded in URLs do not match. Local part is limited to 64 characters. |
| `url` | Absolute URLs with configured schemes, or `www.` addresses. | Defaults: `http`, `https`, `ftp` and `www.`; syntax, host and port are checked without network access. |
| `phone` | North American (`nanp`) and French (`fr`) phone forms. | Defaults include national and supported international prefixes; punctuation and leading digits are checked, but assigned ranges are not. |
| `postal_code` | Canadian postal codes and US ZIP / ZIP+4. | Defaults: `ca`, `us`; `K1A 0B1`, `12345`, `12345-6789`; valid shape does not prove an assigned postal code. |
| `currency` | Number with supported currency symbol or ISO code before or after it. | `$12.50`, `12,50 EUR`; number conventions still apply. |
| `percentage` | Signed number with optional space and `%`. | `12%`, `-2.5 %`; the numeric part is not divided by 100. |
| `quantity` | Number followed by a bounded unit-shaped suffix. | `10m`, `10 Go`, `90 km/h`; currency codes and ordinal endings are excluded, and units are not semantically validated. |
| `uuid` | Hyphenated, braced or `urn:uuid:` 128-bit hexadecimal form. | Case variants are recorded; version and variant are summarized. |
| `ip_address` | IPv4 dotted decimal and IPv6 text, including compressed and embedded-IPv4 forms. | Invalid octets, leading zeros, compression and group counts can be reported. |

`email`, `phone` and `ip_address` are sensitive detectors. When they match a
field, its examples, value profile and preview are masked by default. A
configured pattern can also be sensitive. `postal_code` is not sensitive by
default. See [exposure settings](../configuration.md#sensitive-values-and-sampling).

## Configured patterns

`scan.patterns` adds organization-specific detectors named `pattern:<id>`.
The Python regular expression must match the **whole** value. For example:

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

This recognizes `C-0042` but cannot validate that the customer exists.
`accepts` selects native types (`string`, `integer`, `number`, `boolean`);
`sensitive` controls exposure when the pattern matches; and
`max_input_length` skips longer values. The
[pattern settings](../configuration.md#patterns) specify limits and validation.

## Reading detector evidence

| Result | Meaning | Practical reading |
| --- | --- | --- |
| Matched | The detector recognized the value. | It contributes to a possible semantic-type interpretation. |
| Ambiguous | Several supported readings remain. | It is separate from an unambiguous match; date and number settings can resolve some cases. |
| Invalid | The value has a relevant shape but impossible or disallowed content. | Inspect the value and rule; this is separate from a column type error. |
| Not matched | The detector tested the value and its rule did not fit. | Another detector may still match. |
| Not tested | The value was skipped, for example after adaptive warm-up. | Do not read its match percentage as a complete test of all present values. |
| Failed | Detector processing failed for the field. | The scan diagnostic gives the reason. |

In Report, **Matched** is a count and a percentage of eligible values;
**Ambiguous** and **Invalid** are separate counts. **Formats** gives syntax
labels and counts, which vary by detector and configuration. Adaptive
detection can skip values after its warm-up, while `number` and `date` always
test every eligible value. The [Scan format](../../scan/format.md#detectors)
records every detector's complete coverage and bounded evidence; the
[Report JSON profile](../../report/json-profile.md#detectors) retains its
exposed result. The HTML detector table only lists detectors with evidence or
a failure.
