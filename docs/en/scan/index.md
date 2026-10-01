---
title: Tabalyst Scan
description: Overview of Tabalyst Scan, the analysis engine that describes every field of a CSV, JSON or JSONL file in one JSON document, with commands and pages.
---

**Tabalyst Scan** is the analysis engine of Tabalyst. It reads a CSV, JSON or
JSONL file once, as a stream, and describes every field in one JSON document:
presence, native types, missing values, frequencies, exact statistics,
normalization variants, technical type and the result of every detector.

```console
tabalyst scan customers.csv
tabalyst scan orders.json --collection "$.customers[]"
tabalyst scan events.jsonl
```

Without `-o` or `-d`, the scan is stored for reuse in Tabalyst's local storage.
`-o` or `-d` writes a standalone `<stem>.scan.json` document instead.
[Tabalyst Report](../report/index.md) is built on it, and reuses a stored scan
when the source has not changed.

## What it detects

Numbers with decimal commas, dates, booleans, enumerations, email addresses,
URLs, phone numbers, postal codes, currency amounts, percentages, quantities,
UUIDs and IP addresses. Values of sensitive fields are masked by default.
Memory depends on configurable limits, not on the number of records. Results
are written atomically: an interrupted scan never leaves a partial file.

## Pages

- [Scan CSV and JSON files](files.md): commands, JSON and JSONL sources,
  reuse, settings and the Python API.
- [Scan format](format.md): the structure of the scan document, and its
  [changelog](format-changelog.md).
- [Manage query caches](cache.md): `tabalyst cache info` and
  `tabalyst cache clean`.
- [Configuration](../reference/configuration.md): the `scan` settings.
- [Tabalyst Inspect](../inspect/json.md): how JSON sources are
  read before a scan.
