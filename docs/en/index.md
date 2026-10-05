---
title: Tabalyst documentation
description: Documentation of Tabalyst 0.6.0, the open-source, local-first toolkit that turns CSV, JSON, JSONL and Excel files into reports, JSON profiles, scans and samples.
---

Tabalyst is an open-source, local-first toolkit for understanding unfamiliar
structured data. Install it once and use its tools from the command line or
from Python:

- **[Tabalyst Report](report/index.md)** turns a CSV, JSON, JSONL or Excel file into an interactive
  HTML report and a JSON profile.
- **[Tabalyst Scan](scan/index.md)** describes every field of a file in one JSON document.
- **[Tabalyst Inspect](inspect/index.md)** finds how to read a JSON, JSONL or Excel file.
- **[Tabalyst Sample](sample/index.md)** creates smaller CSV files.

```console
pip install --upgrade tabalyst
tabalyst report customers.csv
```

This creates `customers.html` (the report), `customers.json` (the profile) and
`executions.json` (the run history) beside the CSV file. Everything runs on your
computer; no data is sent anywhere.

Tabalyst is in beta and changes often: run the first command again before each
new test. Commands and the JSON formats may still change between versions. This
documentation describes the latest release published on PyPI.

## What do you want to do?

| Goal | Page |
| --- | --- |
| Install or update Tabalyst | [Install Tabalyst](install.md) |
| Try it step by step | [Create your first report](report/getting-started.md) |
| See a finished report | [Examples and demos](examples.md) |
| Report one or many CSV files | [Report CSV files](report/csv.md) |
| Report a JSON or JSONL file | [Report JSON and JSONL files](report/json.md) |
| Report an Excel workbook | [Report Excel workbooks](report/excel.md) |
| Choose which array of a JSON file is analyzed | [Inspect JSON and JSONL files](inspect/json.md) |
| Choose which sheet or table of a workbook is analyzed | [Inspect Excel workbooks](inspect/excel.md) |
| Describe every field of a file as JSON | [Scan CSV and JSON files](scan/files.md) |
| Cut a large CSV down | [Sample CSV files](sample/index.md) |
| Change delimiter, encoding or detection | [Configuration](reference/configuration.md) |
| Find a command or an option | [Command line (CLI)](reference/cli.md) |
| Use Tabalyst from Python | [Python API](reference/python-api.md) |
| Read a generated JSON file in a script | [JSON profile](report/json-profile.md), [scan format](scan/format.md), [Inspect format](inspect/format.md) |
| Know what is not supported yet | [Known limitations](about/limitations.md) |

## Sections

- **Overview**: this page.
- **Get started**: [install](install.md),
  [first report](report/getting-started.md) and
  [examples and demos](examples.md).
- **Tabalyst Report**: [overview](report/index.md), [CSV](report/csv.md),
  [JSON](report/json.md) and [Excel](report/excel.md) guides, the [JSON profile](report/json-profile.md) and
  its [changelog](report/profile-changelog.md).
- **Tabalyst Inspect**: [overview](inspect/index.md), the
  [JSON](inspect/json.md) and [Excel](inspect/excel.md) guides, the [Inspect format](inspect/format.md) and its
  [changelog](inspect/format-changelog.md).
- **Tabalyst Scan**: [overview](scan/index.md), the
  [guide](scan/files.md), the [scan format](scan/format.md), its
  [changelog](scan/format-changelog.md) and
  [query caches](scan/cache.md).
- **Tabalyst Sample**: [Sample CSV files](sample/index.md).
- **Reference**: [command line](reference/cli.md),
  [Python API](reference/python-api.md),
  [configuration](reference/configuration.md),
  [execution history](reference/history.md) and the
  [glossary](reference/glossary.md).
- **About Tabalyst**: [concepts](about/concepts.md),
  [known limitations](about/limitations.md),
  [release notes](about/releases.md) and
  [contributing and issues](about/contributing.md).

## For AI assistants

To get help from an AI assistant, paste this prompt into a chat that can read
web pages:

```text
Read the complete Tabalyst documentation at
https://docs.tabalyst.com/llms-full.txt, then help me use Tabalyst well.
Ask me what my data looks like and what I want to learn from it, then suggest
the right commands and options. Base your answers only on that documentation.
```

If the assistant cannot open links, paste the content of the file instead.

This site publishes plain-text versions of its pages:

- [llms.txt](https://docs.tabalyst.com/llms.txt) lists every page with a
  one-line description.
- [llms-full.txt](https://docs.tabalyst.com/llms-full.txt) holds the whole
  documentation in one file.
- Every page is also available as Markdown by adding `.md` to its URL, for
  example [report.md](https://docs.tabalyst.com/report.md).
