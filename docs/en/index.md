---
title: Tabalyst documentation
description: Tabalyst is an open-source, local-first toolkit that turns a CSV file into an interactive HTML report and a JSON profile.
---

Tabalyst is an open-source, local-first toolkit for understanding unfamiliar
data. Its first tool, **Tabalyst Report**, analyzes a CSV file and produces an
interactive HTML report and a structured JSON profile.

```console
pip install --upgrade tabalyst
tabalyst report customers.csv
```

This creates `customers.html` (the report), `customers.json` (the profile) and
`executions.json` (the run history) beside the CSV file. Everything runs on your
computer; no data is sent anywhere.

The first command installs Tabalyst, or updates it when it is already
installed. Tabalyst is in alpha and changes often: run it again before each new
test. Commands and the JSON format may still change between versions. This
documentation describes the latest release published on PyPI.

## Start here

- [Install Tabalyst](how-to/install.md), on Windows, macOS or Linux, and
  [keep it up to date](how-to/install.md#keep-tabalyst-up-to-date).
- [Create your first report](tutorials/first-report.md) from a small CSV file.

## Reference

- [JSON profile](reference/json-profile.md): the structure of the generated
  `.json` file.
- [Configuration](reference/configuration.md): the JSON configuration file.
- [Execution history](reference/execution-history.md): the `executions.json`
  file.
- [Profile format changelog](reference/profile-format-changelog.md).
- [Known limitations](reference/known-limitations.md): what Tabalyst does not do
  yet.
- [Glossary](reference/glossary.md): English and French terms.
