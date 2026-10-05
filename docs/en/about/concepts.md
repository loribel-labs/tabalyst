---
title: Concepts
description: How Tabalyst works - the toolkit and its four tools, the workflow from a file to a report, local-first processing, masking of sensitive values, experimental JSON formats and beta status.
---

## The toolkit and its tools

**Tabalyst** is an open-source, local-first toolkit for understanding
unfamiliar structured data. You install Tabalyst, never a single tool, and it
provides:

| Tool | Command | Role |
| --- | --- | --- |
| [Tabalyst Report](../report/index.md) | `tabalyst report` | HTML report and JSON profile |
| [Tabalyst Scan](../scan/index.md) | `tabalyst scan` | Complete JSON description of every field |
| [Tabalyst Inspect](../inspect/json.md) | `tabalyst inspect` | Finds how to read a JSON, JSONL or Excel file |
| [Tabalyst Sample](../sample/index.md) | `tabalyst sample` | Smaller CSV files |

## The workflow

```text
CSV, JSON, JSONL or Excel -> Scan -> scan document -> Report -> HTML report and JSON profile
                      ^
        Inspect (JSON, JSONL and Excel sources: which collection or table, how to flatten)
```

- **Scan** reads the file once, as a stream, and records what it finds about
  each field.
- **Report** builds the profile from the scan, then renders the HTML from the
  profile alone. The profile is the canonical result, for scripts and other
  tools.
- **Inspect** decides how a JSON, JSONL or Excel file is read: which array,
  sheet or table holds the records, and for JSON how nested objects become
  columns named by their path, such as `address.city`. Scan and Report run it by themselves when needed, and use
  your edits of its file when you made some.
- **Sample** is independent: it cuts a CSV file down to a manageable size.

A scan is reused when the source content, the effective configuration and the
Tabalyst version are unchanged; otherwise it is replaced.

## Local-first

Tabalyst analyzes files on your computer, with no telemetry and no remote
processing. The HTML report works without a network connection. Source files
are never modified: Tabalyst only writes new files, and refuses to replace
existing ones without `--force`.

## Sensitive values

Generated JSON and HTML contain values from your source, including a preview of
the first rows. Values of fields detected as sensitive, such as email
addresses and phone numbers, are masked by default. Values of every other field
are listed, so share the outputs as you would share the data.

## Descriptive, not corrective

Detected types, formats and meanings are hints that describe the values.
Tabalyst never converts, repairs or validates your data against business rules,
and ambiguous values, such as the date `02/03/2025`, stay ambiguous unless you
configure how to read them.

## Bounded memory

Reports, scans, samples and Inspect read files as a stream. Memory is bounded
by configurable limits, not by the file size. When a limit is reached, results
show proven lower bounds instead of failing. The detail is in
[Known limitations](limitations.md) and the
[configuration reference](../reference/configuration.md).

## Beta and experimental formats

Tabalyst is in beta until its first stable 1.0 release. Commands and options
may change, and the JSON formats are experimental: the
[JSON profile](../report/json-profile.md), the
[scan format](../scan/format.md) and the
[Inspect format](../inspect/format.md) may change incompatibly between
releases, without migration support. Each has a changelog and carries a
`format_version` and a monotonic `format_revision`; check them before reading a
file. Update with `pip install --upgrade tabalyst`: this documentation describes
the latest release.
