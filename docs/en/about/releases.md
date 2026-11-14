---
title: Release notes
description: A short summary of what changed in each Tabalyst release from 0.1.x to 0.7.6.
---

## 0.7.6

[Tabalyst Report](../report/index.md) counts the combinations of missing
values of a dataset (`missing_patterns`, in the second pass), names the blocks
of columns that go missing together in the report, and `--details` writes a
first [chart page](../report/charts.md), `charts-missing.html`, with an UpSet
plot of those combinations. `--details` now runs the second pass, as `--deep`
does, and the chart pages load Apache ECharts from a CDN (pinned by its SRI
hash); `report.html` still loads nothing from outside. The second-pass document
is at revision 5 and the Report profile at revision 6.

## 0.7.5

[Tabalyst Generate](../generate/index.md) ties the columns of its examples
together, so the files can test analyses across columns: CRM deal amounts,
probabilities and stages, dates in order and sales territories; Insurance
travel contracts, claims and premiums by age; Computer reviews that come with
time. The clean files hold no exception to these rules, and every example gets
a `rule_breaks` profile that breaks them on purpose, each change named in the
change log. The same seed gives different files than with 0.7.4. No JSON format
changes.

## 0.7.4

[Tabalyst Sample](../sample/index.md) gets a second stratified method.
`stratified-balanced` keeps up to `--per-value N` random rows of each value of
one or several fields, and all of a smaller value, so that rare values are well
represented; its size follows from the data. `stratified` now keeps at least one
row of each value, and stops with a clear error when the size asked for is under
the number of values (before, a rare value could get no row, so a sample can
differ from one made with 0.7.3). No JSON format changes.

## 0.7.3

[Tabalyst Generate](../generate/index.md) is much faster for Computer (30,000
rows with errors in two languages in about 17 seconds instead of 8 minutes, and
faster again with several processes) and easier to use for one dataset. `-o` writes a single
Computer CSV, with errors when you give an anomaly profile (`--anomaly-profile`);
`--locales en` or `--locales fr` writes one language; `--anomaly-profile` takes
several profiles to get one variant of each; `--workers` sets the number of
processes. The command shows its progress, with the time left, and ends with a
timing report. The same seed still gives the same data, and no JSON format
changes.

## 0.7.2

Report tells the repetitions of an identifier column that exact copies of whole
rows explain from those between distinct records (`identifier_uniqueness`,
`report --dedup-report`), with a non-binding near-unique reading. The second
pass can count the copies of rows and the distinct values after normalization
(`scan --deep`). Report moves to format revision 5 and the second pass to
revision 4, so older documents must be made again.

## 0.7.1

Adds [Tabalyst Dedup](../dedup/index.md): `tabalyst dedup` finds the exact
duplicate rows of CSV files and writes the unique rows, the repeated rows and
a JSON report, with batches, incremental runs and the Python API
(`dedup_csv`, `generate_dedups`).

## 0.7.0

Reworks Scan and the JSON formats: samples with stated accuracy, inferred
patterns, observations, a Scan web page and a second pass (`scan --plan`,
`scan --deep`) that Report chooses automatically when it pays. Adds smart
samples (`sample --sample-method smart`). Scan and Report move to format
revision 4, so older documents must be made again. Generate now reads package
directories instead of `definition_version: 1` files and adds the Computer
example.

## 0.6.2

Adds [Tabalyst Generate](../generate/index.md) for synthetic CSV datasets from
YAML definitions, with packaged CRM and insurance examples and optional logged
anomaly variants.

## 0.6.1

Makes choosing an Excel table or collection easier. Reorganizes the documentation.

## 0.6.0

Adds support for Excel workbooks.

## 0.5.1

Chooses a JSON collection from `report` and from `inspect`'s own output.

## 0.5.0

Adds Tabalyst Inspect and JSON Lines support.

## 0.4.4

Fast default CSV scans.

## 0.4.3

First beta release.

## 0.4.2

Makes scans several times faster on large files.

## 0.4.1

Adds adaptive detection for columns with many distinct values and a report time
that includes the scan.

## 0.4.0

Introduces Tabalyst Scan, a streaming analysis engine for CSV and JSON.

## 0.3.0

Introduces Tabalyst Sample.

## 0.2.0

Introduces a command-oriented toolkit: `tabalyst report INPUT... [OPTIONS]`.

## 0.1.x

First packaged releases.
